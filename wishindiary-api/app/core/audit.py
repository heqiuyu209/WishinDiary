"""轻量审计日志模块。

将登录、注册、数据修改等敏感操作以结构化 JSON 行写入独立 logger
（`wishindiary.audit`），便于检索与后续接入集中式日志系统。
不引入数据库表，避免与 Alembic 迁移（migrations/versions/）重复维护数据库结构。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

audit_logger = logging.getLogger("wishindiary.audit")


def audit(
    action: str,
    *,
    actor_user_id: int | None = None,
    username: str | None = None,
    ip: str | None = None,
    success: bool = True,
    details: dict[str, Any] | None = None,
) -> None:
    """写一条结构化审计日志，仅保留允许的操作标识，不保存健康日期或正文。"""
    safe_details = {}
    if details and type(details.get("cycle_id")) is int:
        safe_details["cycle_id"] = details["cycle_id"]
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor_user_id": actor_user_id,
        "username": username,
        "ip": ip,
        "success": success,
        "details": safe_details,
    }
    audit_logger.info(json.dumps(record, ensure_ascii=False, default=str))
