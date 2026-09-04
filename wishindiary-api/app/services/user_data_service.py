"""User data business logic（健康数据导出/删除 service 层）。

设计目标：
1. 数据导出：返回当前登录用户全部健康数据（个人资料、周期、每日日志、预测记录），
   便于用户行使数据可携带权 / 留存备份。
2. 数据删除：删除当前用户账号及其全部关联数据（级联清理），
   便于用户行使数据被遗忘权。

统一使用 `with transaction()` 管理事务，AppError 表达可预期失败。
"""

import logging
from datetime import datetime, timezone

import pymysql

from app.core.audit import audit
from app.core.database import transaction
from app.core.errors import AppError

logger = logging.getLogger(__name__)

_EXPORT_TABLES = (
    ("cycles", "cycle_id"),
    ("daily_logs", "log_id"),
    ("prediction_logs", "pred_id"),
)


def _iso(value) -> str | None:
    """将数据库返回的 date/datetime/str 统一转为 ISO 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):  # date
        return value.isoformat()
    return str(value)


def _row_to_json(row: dict) -> dict:
    """把数据库行转为可 JSON 序列化字典（统一日期/时间格式）。"""
    return {k: _iso(v) if isinstance(v, datetime) or hasattr(v, "isoformat") else v for k, v in row.items()}


class UserDataService:
    """用户健康数据导出与账号删除业务。"""

    def export_user_data(self, user_id: int) -> dict:
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT user_id, username, created_at FROM users WHERE user_id = %s",
                        (user_id,),
                    )
                    user = cursor.fetchone()
                    if not user:
                        raise AppError(404, "not_found", "用户不存在")

                    exported: dict = {
                        "user": {
                            "user_id": user["user_id"],
                            "username": user["username"],
                            "created_at": _iso(user["created_at"]),
                        }
                    }
                    for table, id_col in _EXPORT_TABLES:
                        cursor.execute(
                            f"SELECT * FROM {table} WHERE user_id = %s ORDER BY {id_col} ASC",
                            (user_id,),
                        )
                        exported[table] = [_row_to_json(row) for row in cursor.fetchall()]

            audit("user.export", actor_user_id=user_id, success=True)
            return {
                "status": "success",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                **exported,
            }
        except pymysql.err.OperationalError:
            logger.exception("Export failed (db) for user_id=%s", user_id)
            raise AppError(503, "service_unavailable", "数据库连接失败，请稍后重试")
        except AppError:
            raise
        except Exception:
            logger.exception("Export failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "导出失败，请稍后重试")

    def delete_user_data(self, user_id: int) -> dict:
        """删除当前用户账号及其全部关联数据（级联清理）。

        在单个事务中按依赖顺序显式删除子表数据后删除用户行；
        同时依靠外键 ON DELETE CASCADE 作为兜底，保证不残留孤儿数据。
        """
        try:
            with transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
                    if not cursor.fetchone():
                        raise AppError(404, "not_found", "用户不存在")

                    # 显式级联清理（顺序：先子表后主表）
                    for table in ("prediction_logs", "daily_logs", "cycles"):
                        cursor.execute(
                            f"DELETE FROM {table} WHERE user_id = %s",
                            (user_id,),
                        )
                    cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))

            audit("user.delete", actor_user_id=user_id, success=True)
            return {"status": "success", "message": "账号及其全部数据已删除"}
        except pymysql.err.OperationalError:
            logger.exception("Delete user failed (db) for user_id=%s", user_id)
            raise AppError(503, "service_unavailable", "数据库连接失败，请稍后重试")
        except AppError:
            raise
        except Exception:
            logger.exception("Delete user failed for user_id=%s", user_id)
            raise AppError(500, "internal_error", "删除失败，请稍后重试")
