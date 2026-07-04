"""
Stored annotations (Step 7/12) — overlay markup persisted separately from the
baked-into-PDF edits. Backed by the canonical `annotations` table. Mounted at
/api/v1/documents so paths are /documents/{id}/annotations.
"""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from routes import current_user_id, _get_doc_or_404

router = APIRouter()


class CreateAnnotation(BaseModel):
    page_number: int = 1
    type:   str                      # highlight | note | shape | freehand | stamp
    color:  str | None = None
    x:      float | None = None
    y:      float | None = None
    width:  float | None = None
    height: float | None = None
    data:   dict = {}


class UpdateAnnotation(BaseModel):
    color:  str | None = None
    x:      float | None = None
    y:      float | None = None
    width:  float | None = None
    height: float | None = None
    data:   dict | None = None


def _dto(r) -> dict:
    return {
        "id": str(r["id"]), "document_id": str(r["document_id"]),
        "user_id": str(r["user_id"]) if r["user_id"] else None,
        "page_number": r["page_number"], "type": r["type"], "color": r["color"],
        "x": r["x"], "y": r["y"], "width": r["width"], "height": r["height"],
        "data": r["data"], "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


@router.get("/{doc_id}/annotations")
async def list_annotations(doc_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _get_doc_or_404(doc_id, user_id, db)
    rows = (await db.execute(text(
        "SELECT * FROM annotations WHERE document_id = CAST(:d AS uuid) ORDER BY page_number, created_at"),
        {"d": str(doc_id)})).mappings().all()
    return [_dto(r) for r in rows]


@router.post("/{doc_id}/annotations", status_code=201)
async def create_annotation(doc_id: UUID, body: CreateAnnotation,
                            user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    import json
    await _get_doc_or_404(doc_id, user_id, db)
    aid = uuid4()
    await db.execute(text(
        "INSERT INTO annotations (id, document_id, user_id, page_number, type, color, x, y, width, height, data) "
        "VALUES (CAST(:id AS uuid), CAST(:d AS uuid), CAST(:u AS uuid), :pg, :t, :col, :x, :y, :w, :h, CAST(:data AS jsonb))"),
        {"id": str(aid), "d": str(doc_id), "u": str(user_id), "pg": body.page_number, "t": body.type,
         "col": body.color, "x": body.x, "y": body.y, "w": body.width, "h": body.height,
         "data": json.dumps(body.data)})
    row = (await db.execute(text("SELECT * FROM annotations WHERE id = CAST(:id AS uuid)"),
                            {"id": str(aid)})).mappings().first()
    return _dto(row)


@router.patch("/{doc_id}/annotations/{ann_id}")
async def update_annotation(doc_id: UUID, ann_id: UUID, body: UpdateAnnotation,
                            user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    import json
    await _get_doc_or_404(doc_id, user_id, db)
    sets, params = ["updated_at = now()"], {"a": str(ann_id), "d": str(doc_id)}
    for f in ("color", "x", "y", "width", "height"):
        v = getattr(body, f)
        if v is not None:
            sets.append(f"{f} = :{f}"); params[f] = v
    if body.data is not None:
        sets.append("data = CAST(:data AS jsonb)"); params["data"] = json.dumps(body.data)
    res = await db.execute(text(
        f"UPDATE annotations SET {', '.join(sets)} WHERE id = CAST(:a AS uuid) AND document_id = CAST(:d AS uuid)"), params)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"id": str(ann_id), "updated": True}


@router.delete("/{doc_id}/annotations/{ann_id}", status_code=204)
async def delete_annotation(doc_id: UUID, ann_id: UUID,
                            user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _get_doc_or_404(doc_id, user_id, db)
    await db.execute(text(
        "DELETE FROM annotations WHERE id = CAST(:a AS uuid) AND document_id = CAST(:d AS uuid)"),
        {"a": str(ann_id), "d": str(doc_id)})
