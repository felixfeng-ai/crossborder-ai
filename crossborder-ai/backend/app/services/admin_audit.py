"""管理员审计日志写入。"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_audit_log import AdminAuditLog
from app.models.user import User


async def record_admin_action(
    db: AsyncSession,
    admin: User,
    *,
    action: str,
    target_type: str,
    target_id: str,
    changes: dict,
) -> AdminAuditLog:
    """把变更摘要写入审计表，由调用方统一提交事务。"""
    log = AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        changes_json=json.dumps(changes, ensure_ascii=False, default=str),
    )
    db.add(log)
    return log
