"""按保留期限清理 WishinDiary 中已过期的健康数据。

保留期限由环境变量 DATA_RETENTION_DAYS 控制（见 .env.example / app/core/config.py）：
  - 0 或未设置：不清理任何数据（安全默认）；
  - N > 0：删除创建时间早于 (now - N 天) 的周期、每日日志与预测记录。

用途：满足"健康数据保留期限"策略，可配合系统 cron / Windows 计划任务定期执行。
    另外还会清理会话数据：refresh_tokens 表中已撤销/已过期超过 7 天的令牌记录
    （与健康数据保留期无关，见脚本内注释）。

用法：
    python scripts/cleanup_expired_data.py            # 仅预览，不删除
    python scripts/cleanup_expired_data.py --apply    # 真正删除并输出摘要
    python scripts/cleanup_expired_data.py --days 365 # 覆盖 DATA_RETENTION_DAYS

退出码：0 表示成功；任何数据库错误以非 0 退出，并保持事务回滚（不产生半删状态）。
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

import pymysql

# 允许从 wishindiary-api 或仓库根目录两种方式运行
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app.core.config import settings  # noqa: E402

# 涉及的用户数据表（不含 users 本身：不自动删账号）
DATA_TABLES = ("cycles", "daily_logs", "prediction_logs")


def _connect():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _table_cutoff_column(table: str) -> str:
    """每张表用于判断创建时间的列。"""
    return {
        "cycles": "created_at",
        "daily_logs": "created_at",
        "prediction_logs": "created_at",
    }[table]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行删除；缺省时只做预览（不修改数据）。",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="覆盖 DATA_RETENTION_DAYS；0 表示无限期保留。",
    )
    args = parser.parse_args()

    days = args.days if args.days is not None else settings.DATA_RETENTION_DAYS
    if days <= 0:
        print(f"DATA_RETENTION_DAYS={days}（无限期保留），无需清理。")
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    cutoff_sql = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    conn = _connect()
    try:
        total = 0
        for table in DATA_TABLES:
            col = _table_cutoff_column(table)
            where = f"{col} < %s"
            with conn.cursor() as cur:
                cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", (cutoff_sql,))
                count = cur.fetchone()["n"]
            if count:
                if args.apply:
                    with conn.cursor() as cur:
                        cur.execute(f"DELETE FROM {table} WHERE {where}", (cutoff_sql,))
                    print(f"[删除] {table}: {count} 行（创建早于 {cutoff_sql}）")
                else:
                    print(f"[预览] {table}: 将删除 {count} 行（创建早于 {cutoff_sql}）—— 使用 --apply 真正执行")
                total += count

        # 会话数据清理：刷新令牌与用户健康数据保留期无关，单独处理。
        # 清除"已撤销超过 7 天 / 已过期超过 7 天"的令牌记录，
        # 避免 refresh_tokens 表无限增长（保留 7 天缓冲便于近期审计与排查）。
        rt_where = (
            "(revoked_at IS NOT NULL AND revoked_at < NOW() - INTERVAL 7 DAY) "
            "OR (expires_at IS NOT NULL AND expires_at < NOW() - INTERVAL 7 DAY)"
        )
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM refresh_tokens WHERE {rt_where}")
            rt_count = cur.fetchone()["n"]
        if rt_count:
            if args.apply:
                with conn.cursor() as cur:
                    cur.execute(f"DELETE FROM refresh_tokens WHERE {rt_where}")
                print(f"[删除] refresh_tokens: {rt_count} 条（已撤销/已过期超过 7 天）")
            else:
                print(f"[预览] refresh_tokens: 将删除 {rt_count} 条（已撤销/已过期超过 7 天）—— 使用 --apply 真正执行")
            total += rt_count

        if args.apply:
            conn.commit()
            print(f"完成：共清理 {total} 行过期数据。")
        else:
            print(f"预览完成：共 {total} 行将被清理（未做任何修改）。")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
