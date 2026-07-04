"""
Reusable notification writer (notifications table, created by Alembic 0002).

    from shared.notify import notify
    await notify(db, user_id=uid, kind="project.invited", title="Added to a project")

Best-effort: never breaks the primary request path.
"""
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def notify(db: AsyncSession, *, user_id: UUID | str, kind: str, title: str,
                 body: str | None = None, link: str | None = None) -> None:
    try:
        await db.execute(
            text("INSERT INTO notifications (id, user_id, kind, title, body, link) "
                 "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :k, :t, :b, :l)"),
            {"u": str(user_id), "k": kind, "t": title, "b": body, "l": link},
        )
    except Exception:
        pass
