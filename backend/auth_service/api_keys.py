"""
Enterprise API keys (Phase 4 #21) — programmatic access without a user JWT.

- Users mint keys at /api/v1/keys (the raw key is shown ONCE, only a SHA-256 hash is stored).
- The gateway resolves an `X-API-Key` header to a user via the internal /internal/validate-key
  endpoint, then injects the usual x-user-* headers — so every existing API works with a key.
"""
import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.audit import record as audit
from models import User
from routes import _get_current_user

keys_router          = APIRouter()   # mounted at /api/v1/keys
keys_internal_router = APIRouter()   # mounted at /internal


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class CreateKey(BaseModel):
    name: str


@keys_router.post("", status_code=201)
async def create_key(body: CreateKey, current_user: User = Depends(_get_current_user),
                     db: AsyncSession = Depends(get_db)):
    raw    = "pk_" + secrets.token_urlsafe(32)
    prefix = raw[:12]
    await db.execute(text(
        "INSERT INTO api_keys (id, user_id, name, key_hash, prefix) "
        "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :n, :h, :p)"),
        {"u": str(current_user.id), "n": body.name, "h": _hash(raw), "p": prefix})
    await audit(db, action="apikey.created", user_id=current_user.id, resource="api_key",
                metadata={"name": body.name})
    # raw key returned exactly once
    return {"name": body.name, "key": raw, "prefix": prefix}


@keys_router.get("")
async def list_keys(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT id, name, prefix, last_used_at, revoked_at, created_at FROM api_keys "
        "WHERE user_id = CAST(:u AS uuid) ORDER BY created_at DESC"), {"u": str(current_user.id)})).mappings().all()
    return [
        {"id": str(r["id"]), "name": r["name"], "prefix": r["prefix"],
         "revoked": r["revoked_at"] is not None,
         "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
         "created_at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows
    ]


@keys_router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: UUID, current_user: User = Depends(_get_current_user),
                     db: AsyncSession = Depends(get_db)):
    await db.execute(text(
        "UPDATE api_keys SET revoked_at = now() "
        "WHERE id = CAST(:k AS uuid) AND user_id = CAST(:u AS uuid) AND revoked_at IS NULL"),
        {"k": str(key_id), "u": str(current_user.id)})


class ValidateKey(BaseModel):
    key: str


@keys_internal_router.post("/validate-key")
async def validate_key(body: ValidateKey, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(text(
        "SELECT k.id, u.id AS user_id, u.email, u.role FROM api_keys k "
        "JOIN users u ON u.id = k.user_id "
        "WHERE k.key_hash = :h AND k.revoked_at IS NULL AND u.is_active = TRUE"),
        {"h": _hash(body.key)})).mappings().first()
    if not row:
        return {"valid": False, "user_id": "", "email": "", "role": ""}
    await db.execute(text("UPDATE api_keys SET last_used_at = now() WHERE id = :k"), {"k": row["id"]})
    return {"valid": True, "user_id": str(row["user_id"]), "email": row["email"], "role": row["role"]}
