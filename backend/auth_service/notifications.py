"""
In-app notifications API (Phase 4). User-scoped read/mark-read over the
notifications table. Notifications are written by services via shared.notify.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from models import User
from routes import _get_current_user

notifications_router = APIRouter()


@notifications_router.get("")
async def list_notifications(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
):
    clause = "AND read_at IS NULL" if unread_only else ""
    rows = (await db.execute(text(
        f"SELECT id, kind, title, body, link, read_at, created_at FROM notifications "
        f"WHERE user_id = CAST(:u AS uuid) {clause} ORDER BY created_at DESC LIMIT :lim"),
        {"u": str(current_user.id), "lim": limit})).mappings().all()
    return [
        {"id": str(r["id"]), "kind": r["kind"], "title": r["title"], "body": r["body"],
         "link": r["link"], "read": r["read_at"] is not None,
         "created_at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows
    ]


@notifications_router.get("/unread-count")
async def unread_count(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    n = (await db.execute(text(
        "SELECT count(*) FROM notifications WHERE user_id = CAST(:u AS uuid) AND read_at IS NULL"),
        {"u": str(current_user.id)})).scalar()
    return {"unread": int(n or 0)}


@notifications_router.post("/{notification_id}/read")
async def mark_read(notification_id: UUID, current_user: User = Depends(_get_current_user),
                    db: AsyncSession = Depends(get_db)):
    await db.execute(text(
        "UPDATE notifications SET read_at = now() "
        "WHERE id = CAST(:n AS uuid) AND user_id = CAST(:u AS uuid) AND read_at IS NULL"),
        {"n": str(notification_id), "u": str(current_user.id)})
    return {"ok": True}


@notifications_router.post("/read-all")
async def mark_all_read(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text(
        "UPDATE notifications SET read_at = now() WHERE user_id = CAST(:u AS uuid) AND read_at IS NULL"),
        {"u": str(current_user.id)})
    return {"ok": True}
