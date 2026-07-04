"""
Projects / Team Workspaces (Phase 4).

A project groups documents and has members with roles (owner | editor | viewer).
Uses raw SQL against the projects / project_members / project_documents tables
(created by Alembic 0002). Membership is the access-control boundary.
"""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.audit import record as audit
from shared.notify import notify
from routes import current_user_id, _get_doc_or_404

router = APIRouter()


# ── Access helpers ────────────────────────────────────────────────────────────

async def _role(db: AsyncSession, project_id: UUID, user_id: UUID) -> str | None:
    """Return the caller's role on a project (owner via projects.owner_id, or membership)."""
    owner = (await db.execute(text(
        "SELECT 1 FROM projects WHERE id = CAST(:p AS uuid) AND owner_id = CAST(:u AS uuid)"),
        {"p": str(project_id), "u": str(user_id)})).first()
    if owner:
        return "owner"
    row = (await db.execute(text(
        "SELECT role FROM project_members WHERE project_id = CAST(:p AS uuid) AND user_id = CAST(:u AS uuid)"),
        {"p": str(project_id), "u": str(user_id)})).first()
    return row[0] if row else None


async def _require_role(db, project_id, user_id, *allowed) -> str:
    role = await _role(db, project_id, user_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if allowed and role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient project permissions")
    return role


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateProject(BaseModel):
    name: str
    description: str | None = None


class AddMember(BaseModel):
    user_id: str
    role: str = "viewer"   # editor | viewer


class AddDocument(BaseModel):
    document_id: str


# ── Projects CRUD ─────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_project(body: CreateProject, request: Request,
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    pid = uuid4()
    await db.execute(text(
        "INSERT INTO projects (id, owner_id, name, description) "
        "VALUES (CAST(:id AS uuid), CAST(:u AS uuid), :n, :d)"),
        {"id": str(pid), "u": str(user_id), "n": body.name, "d": body.description})
    await audit(db, action="project.created", user_id=user_id, resource="project", resource_id=pid, request=request)
    return {"id": str(pid), "name": body.name, "description": body.description, "role": "owner"}


@router.get("")
async def list_projects(user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT p.id, p.name, p.description, "
        "CASE WHEN p.owner_id = CAST(:u AS uuid) THEN 'owner' ELSE m.role END AS role "
        "FROM projects p "
        "LEFT JOIN project_members m ON m.project_id = p.id AND m.user_id = CAST(:u AS uuid) "
        "WHERE p.owner_id = CAST(:u AS uuid) OR m.user_id = CAST(:u AS uuid) "
        "ORDER BY p.created_at DESC"), {"u": str(user_id)})).mappings().all()
    return [{"id": str(r["id"]), "name": r["name"], "description": r["description"], "role": r["role"]} for r in rows]


@router.get("/{project_id}")
async def get_project(project_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    role = await _require_role(db, project_id, user_id)
    p = (await db.execute(text("SELECT id, name, description FROM projects WHERE id = CAST(:p AS uuid)"),
                          {"p": str(project_id)})).mappings().first()
    members = (await db.execute(text(
        "SELECT user_id, role FROM project_members WHERE project_id = CAST(:p AS uuid)"),
        {"p": str(project_id)})).mappings().all()
    docs = (await db.execute(text(
        "SELECT document_id FROM project_documents WHERE project_id = CAST(:p AS uuid)"),
        {"p": str(project_id)})).scalars().all()
    return {"id": str(p["id"]), "name": p["name"], "description": p["description"], "role": role,
            "members": [{"user_id": str(m["user_id"]), "role": m["role"]} for m in members],
            "document_ids": [str(d) for d in docs]}


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _require_role(db, project_id, user_id, "owner")
    await db.execute(text("DELETE FROM projects WHERE id = CAST(:p AS uuid)"), {"p": str(project_id)})


# ── Members ───────────────────────────────────────────────────────────────────

@router.post("/{project_id}/members", status_code=201)
async def add_member(project_id: UUID, body: AddMember,
                     user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _require_role(db, project_id, user_id, "owner")
    if body.role not in ("editor", "viewer"):
        raise HTTPException(status_code=400, detail="role must be editor or viewer")
    await db.execute(text(
        "INSERT INTO project_members (id, project_id, user_id, role) "
        "VALUES (uuid_generate_v4(), CAST(:p AS uuid), CAST(:u AS uuid), :r) "
        "ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role"),
        {"p": str(project_id), "u": body.user_id, "r": body.role})
    await notify(db, user_id=body.user_id, kind="project.invited",
                 title="You were added to a project", link=f"/projects/{project_id}")
    return {"project_id": str(project_id), "user_id": body.user_id, "role": body.role}


@router.delete("/{project_id}/members/{member_id}", status_code=204)
async def remove_member(project_id: UUID, member_id: UUID,
                        user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _require_role(db, project_id, user_id, "owner")
    await db.execute(text(
        "DELETE FROM project_members WHERE project_id = CAST(:p AS uuid) AND user_id = CAST(:m AS uuid)"),
        {"p": str(project_id), "m": str(member_id)})


# ── Documents in a project ────────────────────────────────────────────────────

@router.post("/{project_id}/documents", status_code=201)
async def add_document(project_id: UUID, body: AddDocument,
                       user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _require_role(db, project_id, user_id, "owner", "editor")
    # caller must own the document being added
    await _get_doc_or_404(UUID(body.document_id), user_id, db)
    await db.execute(text(
        "INSERT INTO project_documents (id, project_id, document_id) "
        "VALUES (uuid_generate_v4(), CAST(:p AS uuid), CAST(:d AS uuid)) ON CONFLICT DO NOTHING"),
        {"p": str(project_id), "d": body.document_id})
    return {"project_id": str(project_id), "document_id": body.document_id}


@router.delete("/{project_id}/documents/{document_id}", status_code=204)
async def remove_document(project_id: UUID, document_id: UUID,
                          user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _require_role(db, project_id, user_id, "owner", "editor")
    await db.execute(text(
        "DELETE FROM project_documents WHERE project_id = CAST(:p AS uuid) AND document_id = CAST(:d AS uuid)"),
        {"p": str(project_id), "d": str(document_id)})
