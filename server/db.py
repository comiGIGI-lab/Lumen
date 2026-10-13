# -*- coding: utf-8 -*-
"""MySQL 访问层 —— 全仓库唯一允许 import pymysql 的地方（与 storage_* 模块一起）。

约束（NFR-01 已于 2026-10-11 经用户正式解除，仅限本存储层）：
    - quiz.py / 向量 RAG 等核心零依赖模块**绝不** import mysql，否则回归闸变红；
    - 只有本文件与 server/storage_*.py 可触达 pymysql。

连接参数从环境变量读取（兼容 .env；api_server 用标准库在 import 前预加载）：
    STUDY_LIU_MYSQL_HOST     默认 localhost
    STUDY_LIU_MYSQL_PORT     默认 3306
    STUDY_LIU_MYSQL_USER     默认 root
    STUDY_LIU_MYSQL_PASSWORD 默认空
    STUDY_LIU_MYSQL_DATABASE 默认 study_liu
    STUDY_LIU_MYSQL_CHARSET  默认 utf8mb4

容错：pymysql 惰性导入，未安装时 `import db` 不报错，仅在真正访问数据库时抛
DbUnavailable，storage 层据此降级到 JSON 兜底（保证回归测试与数据库宕机时仍可用）。
"""

import os
import threading


class DbUnavailable(Exception):
    """MySQL 不可用：未配置 / 连不上 / 驱动缺失。storage 层应捕获并降级。"""


_CFG = None
_LOCK = threading.Lock()


def configure():
    """读取环境变量，构建连接配置（幂等，可重复调用）。"""
    global _CFG
    with _LOCK:
        _CFG = {
            "host": os.environ.get("STUDY_LIU_MYSQL_HOST", "localhost"),
            "port": int(os.environ.get("STUDY_LIU_MYSQL_PORT", "3306")),
            "user": os.environ.get("STUDY_LIU_MYSQL_USER", "root"),
            "password": os.environ.get("STUDY_LIU_MYSQL_PASSWORD", ""),
            "database": os.environ.get("STUDY_LIU_MYSQL_DATABASE", "study_liu"),
            "charset": os.environ.get("STUDY_LIU_MYSQL_CHARSET", "utf8mb4"),
            "connect_timeout": int(os.environ.get("STUDY_LIU_MYSQL_TIMEOUT", "5")),
            "autocommit": True,
        }
    return _CFG


def _cfg():
    global _CFG
    if _CFG is None:
        configure()
    return _CFG


def _pymysql():
    try:
        import pymysql
        return pymysql
    except ImportError as exc:  # pragma: no cover - 依赖缺失
        raise DbUnavailable("PyMySQL 未安装：pip install PyMySQL") from exc


def get_conn():
    """返回一个新的 PyMySQL 连接（autocommit）。失败抛 DbUnavailable。"""
    cfg = _cfg()
    pym = _pymysql()
    try:
        return pym.connect(
            host=cfg["host"], port=cfg["port"], user=cfg["user"],
            password=cfg["password"], database=cfg["database"],
            charset=cfg["charset"], connect_timeout=cfg["connect_timeout"],
            autocommit=cfg["autocommit"],
        )
    except DbUnavailable:
        raise
    except Exception as exc:
        raise DbUnavailable("MySQL 连接失败：%s" % exc) from exc


def split_bucket(bucket):
    """把归属桶名拆成 (owner_username, client_id)。

        "u:alice" -> ("alice", None)
        "c-1"     -> (None, "c-1")
        "" / None -> (None, None)
    """
    if not bucket:
        return (None, None)
    b = bucket.strip()
    if b.startswith("u:"):
        return (b[2:], None)
    return (None, b)


def ensure_schema(schema_path=None):
    """幂等建表：执行 db/schema.sql（CREATE TABLE IF NOT EXISTS）。"""
    if schema_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(os.path.dirname(here), "db", "schema.sql")
    if not os.path.exists(schema_path):
        raise DbUnavailable("找不到 schema 文件：%s" % schema_path)
    with open(schema_path, encoding="utf-8") as f:
        sql = f.read()
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for stmt in _split_statements(sql):
                if stmt.strip():
                    cur.execute(stmt)
            # 既有库补齐进度归属列（幂等，不破坏已存在结构）
            _ensure_progress_owner_columns(cur)
        conn.commit()
    finally:
        conn.close()


def _split_statements(sql):
    """按分号切分 DDL（schema 无存储过程 / 无字符串内分号，足够）。"""
    out, buf = [], []
    for line in sql.splitlines():
        s = line.strip()
        if not s or s.startswith("--"):
            continue
        buf.append(line)
        if s.endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out


def _ensure_progress_owner_columns(cur):
    """为既有库补齐进度表的 owner / importance 列与复合主键（幂等）。

    新库由 schema.sql 直接建好，这里对老库做 ALTER：
      - plan_items 加 owner / importance，并加索引 idx_pi_owner(owner, course_id)
      - plan_results 加 owner，并把主键改为 (course_id, owner)
    老库里既有的全局行 owner 留空 ''，新写入按归属隔离，互不影响。
    """
    def _has_col(table, col):
        cur.execute(
            "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s AND COLUMN_NAME=%s",
            (table, col))
        return cur.fetchone() is not None

    if not _has_col("plan_items", "owner"):
        cur.execute(
            "ALTER TABLE plan_items ADD COLUMN owner VARCHAR(96) NOT NULL DEFAULT ''")
    if not _has_col("plan_items", "importance"):
        cur.execute(
            "ALTER TABLE plan_items ADD COLUMN importance TINYINT(1) NOT NULL DEFAULT 0")
    cur.execute("SHOW INDEX FROM plan_items WHERE Key_name='idx_pi_owner'")
    if cur.fetchone() is None:
        cur.execute(
            "ALTER TABLE plan_items ADD KEY idx_pi_owner (owner, course_id)")

    if not _has_col("plan_results", "owner"):
        cur.execute(
            "ALTER TABLE plan_results ADD COLUMN owner VARCHAR(96) NOT NULL DEFAULT ''")

    # 主键要改成 (course_id, owner)。⚠️ 两个坑（2026-10-13 线上踩过）：
    #   1) 老库 plan_results 上有外键 fk_pr_course 指着 course_id，而 MySQL
    #      **不允许删掉外键所依赖的索引**（旧主键就是它）——必须先卸外键。
    #   2) 原来把 DROP PRIMARY KEY 包在 `except Exception: pass` 里，异常被吞掉后
    #      紧接的 ADD PRIMARY KEY 报 1068 Multiple primary key defined，
    #      导致整个 ensure_schema 抛错、**全库退回 JSON 兜底**（静默降级）。
    # 改成：按 INFORMATION_SCHEMA 判断主键是否已含 owner（幂等 + 可自愈），
    # 需要改时严格按「卸外键 → 卸主键 → 建复合主键 → 重建外键」四步来，不吞异常。
    cur.execute(
        "SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) "
        "FROM INFORMATION_SCHEMA.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'plan_results' "
        "AND index_name = 'PRIMARY'")
    row = cur.fetchone()
    pk_cols = (row[0] if row and row[0] else "") or ""
    if "owner" not in pk_cols:
        cur.execute(
            "SELECT constraint_name FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'plan_results' "
            "AND referenced_table_name IS NOT NULL LIMIT 1")
        fk_row = cur.fetchone()
        fk_name = fk_row[0] if fk_row else None
        if fk_name:
            cur.execute("ALTER TABLE plan_results DROP FOREIGN KEY %s" % fk_name)
        cur.execute("ALTER TABLE plan_results DROP PRIMARY KEY")
        cur.execute(
            "ALTER TABLE plan_results ADD PRIMARY KEY (course_id, owner)")
        if fk_name:
            cur.execute(
                "ALTER TABLE plan_results ADD CONSTRAINT fk_pr_course "
                "FOREIGN KEY (course_id) REFERENCES plan_courses (id) "
                "ON DELETE CASCADE")
