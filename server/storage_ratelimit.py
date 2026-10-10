"""匿名用户 LLM 调用限速（防团队 token 被刷完）。

双闸（同一 rate_limits 表，按 bucket 区分）：
  · 每浏览器每日上限  bucket = "anon:<client_id>"  —— 环境变量 STUDY_LIU_ANON_DAILY_LIMIT，默认 10
  · 全局匿名每日池    bucket = "anon:global"        —— 环境变量 STUDY_LIU_ANON_GLOBAL_DAILY_LIMIT，默认 200

登录用户不受此限（视为可信队友，详见 api_server._enforce_anon_llm_quota）。

存储：MySQL rate_limits 表（与用户系统同一库，复用 db 连接，PyMySQL 仅在此 + db.py 出现）。
MySQL 不可用（DbUnavailable）或任何数据库异常时 fail-open 放行，避免数据库抖动把全站请求挡在门外。
"""
import os
import time
import datetime
import pymysql

import db


def _today() -> str:
    """本地日期，用作每日计数窗口键（YYYY-MM-DD）。"""
    return datetime.date.today().isoformat()


def _to_int(val, default: int) -> int:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return default


def anon_per_browser_limit() -> int:
    """每浏览器每日匿名 AI 调用上限。"""
    return _to_int(os.environ.get("STUDY_LIU_ANON_DAILY_LIMIT"), 10)


def anon_global_limit() -> int:
    """全局匿名每日 AI 调用池上限。"""
    return _to_int(os.environ.get("STUDY_LIU_ANON_GLOBAL_DAILY_LIMIT"), 200)


def check_and_incr(bucket: str, day: str, limit: int) -> bool:
    """原子地尝试预留一次调用额度。

    返回 True = 放行（已 +1 或无需限制）；False = 拦截（已达上限）。
    limit<=0 视为不限制。MySQL 异常一律 fail-open 放行。
    """
    if limit is None or limit <= 0:
        return True
    try:
        conn = db.get_conn()
    except db.DbUnavailable:
        return True
    try:
        with conn.cursor() as cur:
            # 仅在当前 count < limit 时 +1，天然实现「允许 1..limit，拦截 limit+1」。
            cur.execute(
                "UPDATE rate_limits SET count=count+1, updated_at=%s "
                "WHERE bucket=%s AND day=%s AND count < %s",
                (int(time.time() * 1000), bucket, day, int(limit)),
            )
            if cur.rowcount == 0:
                # 两种可能：行不存在（首位请求）或 count>=limit（已达上限）。
                try:
                    cur.execute(
                        "INSERT INTO rate_limits (bucket, day, count, updated_at) "
                        "VALUES (%s, %s, 1, %s)",
                        (bucket, day, int(time.time() * 1000)),
                    )
                except pymysql.IntegrityError:
                    # 行已存在且 UPDATE 未命中 → 并发首位请求竞争，或确已达标。
                    # 重新读取当前值判定：仍 <limit 说明并发下本应放行，否则拦截。
                    cur.execute(
                        "SELECT count FROM rate_limits WHERE bucket=%s AND day=%s",
                        (bucket, day),
                    )
                    row = cur.fetchone()
                    return row is not None and row[0] < limit
            return True
    except db.DbUnavailable:
        return True
    except Exception:
        # 任何数据库异常都 fail-open，绝不因限速把正常请求挡在门外
        return True
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _reset_for_test(bucket: str, day: str):
    """仅供测试：清空某桶当日计数。"""
    try:
        conn = db.get_conn()
    except db.DbUnavailable:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rate_limits WHERE bucket=%s AND day=%s",
                (bucket, day),
            )
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
