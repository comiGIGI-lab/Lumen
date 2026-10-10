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
