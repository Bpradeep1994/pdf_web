"""
Folder system (PDFForge Phase 2). Nestable folders owned by a user; documents
reference a folder via documents.folder_id (Alembic 0004). Raw SQL to stay aligned
with the SQL-first schema.
"""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from routes import current_user_id

router = APIRouter()


class CreateFolder(BaseModel):
    name: str
    parent_id: str | None = None


class RenameFolder(BaseModel):
    name: str


async def _own_folder(db, folder_id, user_id):
    row = (await db.execute(text(
        "SELECT 1 FROM folders WHERE id = CAST(:f AS uuid) AND owner_id = CAST(:u AS uuid)"),
        {"f": str(folder_id), "u": str(user_id)})).first()
    if not row:
        raise HTTPException(status_code=404, detail="Folder not found")


@router.post("", status_code=201)
async def create_folder(body: CreateFolder, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    if body.parent_id:
        await _own_folder(db, body.parent_id, user_id)
    fid = uuid4()
    await db.execute(text(
        "INSERT INTO folders (id, owner_id, name, parent_id) "
        "VALUES (CAST(:id AS uuid), CAST(:u AS uuid), :n, CAST(:p AS uuid))"),
        {"id": str(fid), "u": str(user_id), "n": body.name, "p": body.parent_id})
    return {"id": str(fid), "name": body.name, "parent_id": body.parent_id}


@router.get("")
async def list_folders(parent_id: str | None = None,
                       user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    if parent_id:
        rows = (await db.execute(text(
            "SELECT id, name, parent_id FROM folders WHERE owner_id = CAST(:u AS uuid) "
            "AND parent_id = CAST(:p AS uuid) ORDER BY name"), {"u": str(user_id), "p": parent_id})).mappings().all()
    else:
        rows = (await db.execute(text(
            "SELECT id, name, parent_id FROM folders WHERE owner_id = CAST(:u AS uuid) "
            "AND parent_id IS NULL ORDER BY name"), {"u": str(user_id)})).mappings().all()
    return [{"id": str(r["id"]), "name": r["name"],
             "parent_id": str(r["parent_id"]) if r["parent_id"] else None} for r in rows]


@router.patch("/{folder_id}")
async def rename_folder(folder_id: UUID, body: RenameFolder,
                        user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _own_folder(db, folder_id, user_id)
    await db.execute(text("UPDATE folders SET name = :n, updated_at = now() WHERE id = CAST(:f AS uuid)"),
                     {"n": body.name, "f": str(folder_id)})
    return {"id": str(folder_id), "name": body.name}


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _own_folder(db, folder_id, user_id)
    await db.execute(text("DELETE FROM folders WHERE id = CAST(:f AS uuid)"), {"f": str(folder_id)})


@router.get("/{folder_id}/documents")
async def folder_documents(folder_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _own_folder(db, folder_id, user_id)
    rows = (await db.execute(text(
        "SELECT id, original_name, file_size, page_count, status FROM documents "
        "WHERE folder_id = CAST(:f AS uuid) AND owner_id = CAST(:u AS uuid) ORDER BY created_at DESC"),
        {"f": str(folder_id), "u": str(user_id)})).mappings().all()
    return [{"id": str(r["id"]), "original_name": r["original_name"], "file_size": r["file_size"],
             "page_count": r["page_count"], "status": r["status"]} for r in rows]
