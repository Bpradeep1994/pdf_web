"""
Comments + mentions (PDFForge Phase 9). Uses the canonical document_comments table.
Threaded (parent_id), optionally pinned to a page coordinate, resolvable, with
@mentions that generate notifications. Mounted at /api/v1/documents.
"""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.notify import notify
from routes import current_user_id, _get_doc_or_404

router = APIRouter()


class CreateComment(BaseModel):
    content:   str
    page:      int | None = None
    x:         float | None = None
    y:         float | None = None
    parent_id: str | None = None
    mentions:  list[str] = []     # user_ids to @mention


class UpdateComment(BaseModel):
    content:  str | None = None
    resolved: bool | None = None


def _dto(r) -> dict:
    return {"id": str(r["id"]), "user_id": str(r["user_id"]) if r["user_id"] else None,
            "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
            "page": r["page_number"], "x": r["x"], "y": r["y"], "content": r["content"],
            "resolved": r["resolved"], "created_at": r["created_at"].isoformat() if r["created_at"] else None}


@router.get("/{doc_id}/comments")
async def list_comments(doc_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _get_doc_or_404(doc_id, user_id, db)
    rows = (await db.execute(text(
        "SELECT id, user_id, parent_id, page_number, x, y, content, resolved, created_at "
        "FROM document_comments WHERE document_id = CAST(:d AS uuid) ORDER BY created_at ASC"),
        {"d": str(doc_id)})).mappings().all()
    return [_dto(r) for r in rows]


@router.post("/{doc_id}/comments", status_code=201)
async def create_comment(doc_id: UUID, body: CreateComment,
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _get_doc_or_404(doc_id, user_id, db)
    cid = uuid4()
    await db.execute(text(
        "INSERT INTO document_comments (id, document_id, user_id, parent_id, page_number, x, y, content) "
        "VALUES (CAST(:id AS uuid), CAST(:d AS uuid), CAST(:u AS uuid), CAST(:p AS uuid), :pg, :x, :y, :c)"),
        {"id": str(cid), "d": str(doc_id), "u": str(user_id), "p": body.parent_id,
         "pg": body.page, "x": body.x, "y": body.y, "c": body.content})
    for mentioned in body.mentions:
        await notify(db, user_id=mentioned, kind="comment.mention",
                     title="You were mentioned in a comment", link=f"/editor/{doc_id}")
    row = (await db.execute(text(
        "SELECT id, user_id, parent_id, page_number, x, y, content, resolved, created_at "
        "FROM document_comments WHERE id = CAST(:id AS uuid)"), {"id": str(cid)})).mappings().first()
    return _dto(row)


@router.patch("/{doc_id}/comments/{comment_id}")
async def update_comment(doc_id: UUID, comment_id: UUID, body: UpdateComment,
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _get_doc_or_404(doc_id, user_id, db)
    sets, params = [], {"c": str(comment_id), "d": str(doc_id)}
    if body.content is not None:  sets.append("content = :content"); params["content"] = body.content
    if body.resolved is not None: sets.append("resolved = :resolved"); params["resolved"] = body.resolved
    if not sets:
        raise HTTPException(status_code=400, detail="nothing to update")
    sets.append("updated_at = now()")
    res = await db.execute(text(
        f"UPDATE document_comments SET {', '.join(sets)} "
        f"WHERE id = CAST(:c AS uuid) AND document_id = CAST(:d AS uuid)"), params)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"id": str(comment_id), **{k: v for k, v in params.items() if k in ("content", "resolved")}}


@router.delete("/{doc_id}/comments/{comment_id}", status_code=204)
async def delete_comment(doc_id: UUID, comment_id: UUID,
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _get_doc_or_404(doc_id, user_id, db)
    await db.execute(text(
        "DELETE FROM document_comments WHERE id = CAST(:c AS uuid) AND document_id = CAST(:d AS uuid)"),
        {"c": str(comment_id), "d": str(doc_id)})
