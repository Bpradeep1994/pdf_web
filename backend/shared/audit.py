"""
Reusable audit-log writer (canonical audit_logs table).

Any service sharing the database can record security/business events:

    from shared.audit import record
    await record(db, user_id=uid, action="user.login", request=request)

Columns map to database/migrations/001_init.sql:
  user_id, action, resource, resource_id (uuid|null), metadata (jsonb),
  ip_address (inet|null), user_agent.
"""
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record(
    db: AsyncSession,
    *,
    action: str,
    user_id: UUID | str | None = None,
    resource: str | None = None,
    resource_id: UUID | str | None = None,
    request=None,
    metadata: dict | None = None,
) -> None:
    try:
        await db.execute(
            text(
                "INSERT INTO audit_logs (id, user_id, action, resource, resource_id, metadata, ip_address, user_agent) "
                "VALUES (uuid_generate_v4(), CAST(:uid AS uuid), :action, :resource, CAST(:rid AS uuid), "
                "CAST(:meta AS jsonb), :ip, :ua)"
            ),
            {
                "uid": str(user_id) if user_id else None,
                "action": action,
                "resource": resource,
                "rid": str(resource_id) if resource_id else None,
                "meta": json.dumps(metadata or {}),
                "ip": (request.client.host if request and request.client else None),
                "ua": (request.headers.get("user-agent") if request else None),
            },
        )
    except Exception:
        # Auditing must never break the primary request path.
        pass
