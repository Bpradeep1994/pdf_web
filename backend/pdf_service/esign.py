"""
E-Signature API (Phase 3) â€” built on the canonical schema (signature_requests,
signature_fields, audit_logs from database/migrations/001_init.sql).

- Self-sign: stamp a signature image onto your own document at a location â†’ new version.
- Signature requests: create a request with placed fields (one per signer), signers
  apply their signature image; when all fields are signed the request is completed and
  a final signed document version is produced.
- Every signing action is recorded in audit_logs (user, IP, user-agent, timestamp).

Uses raw SQL against the canonical tables (no ORM models) to stay aligned with the
authoritative schema. PDF stamping uses PyMuPDF insert_image.
"""
import base64
import io
from uuid import UUID, uuid4

import fitz
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.s3 import download_file
from routes import current_user_id, _get_doc_or_404, _save_new_version

router = APIRouter()


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _decode_png(b64: str) -> bytes:
    try:
        return base64.b64decode(b64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 signature image")


def _stamp_image(src_path: str, out_path: str, page_no: int, rect: list[float], image_bytes: bytes) -> None:
    pdf  = fitz.open(src_path)
    if page_no < 1 or page_no > len(pdf):
        pdf.close()
        raise HTTPException(status_code=400, detail=f"Invalid page {page_no} (document has {len(pdf)} pages)")
    pdf[page_no - 1].insert_image(fitz.Rect(rect), stream=image_bytes, keep_proportion=True)
    pdf.save(out_path)
    pdf.close()


async def _audit(db: AsyncSession, user_id: UUID, action: str, resource_id: UUID, request: Request | None):
    await db.execute(
        text("INSERT INTO audit_logs (id, user_id, action, resource, resource_id, ip_address, user_agent) "
             "VALUES (uuid_generate_v4(), CAST(:uid AS uuid), :action, 'document', CAST(:rid AS uuid), "
             ":ip, :ua)"),
        {"uid": str(user_id), "action": action, "rid": str(resource_id),
         "ip": (request.client.host if request and request.client else None),
         "ua": (request.headers.get("user-agent") if request else None)},
    )


# â”€â”€ Self-sign â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ApplySignature(BaseModel):
    document_id:      str
    signature_base64: str
    page:   int   = 1
    x:      float
    y:      float
    width:  float = 150
    height: float = 50


@router.post("/apply")
async def apply_signature(body: ApplySignature, request: Request,
                          user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(UUID(body.document_id), user_id, db)
    img = _decode_png(body.signature_base64)

    tmp_in  = f"/tmp/sign_{doc.id}_in.pdf"
    tmp_out = f"/tmp/sign_{doc.id}_out.pdf"
    download_file(doc.s3_key, tmp_in)
    _stamp_image(tmp_in, tmp_out, body.page, [body.x, body.y, body.x + body.width, body.y + body.height], img)

    await _save_new_version(doc, tmp_out, user_id, db)
    await _audit(db, user_id, "signature.applied", doc.id, request)
    return {"message": "Document signed", "document_id": str(doc.id)}


# â”€â”€ Signature requests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class FieldIn(BaseModel):
    signer_email: str
    page_number:  int = 1
    x:      float = 0
    y:      float = 0
    width:  float = 150
    height: float = 50
    field_type: str = "signature"


class CreateRequest(BaseModel):
    document_id: str
    title:       str | None = None
    message:     str | None = None
    fields:      list[FieldIn]


async def _request_dto(db: AsyncSession, req_id: UUID) -> dict:
    req = (await db.execute(text(
        "SELECT id, document_id, title, message, status, completed_at, signed_doc_key "
        "FROM signature_requests WHERE id = CAST(:id AS uuid)"), {"id": str(req_id)})).mappings().first()
    fields = (await db.execute(text(
        "SELECT id, signer_email, page_number, x, y, width, height, field_type, signed_at, "
        "(signature IS NOT NULL) AS signed FROM signature_fields WHERE request_id = CAST(:id AS uuid) "
        "ORDER BY page_number, y"), {"id": str(req_id)})).mappings().all()
    return {
        "id": str(req["id"]), "document_id": str(req["document_id"]), "title": req["title"],
        "message": req["message"], "status": req["status"],
        "completed_at": req["completed_at"].isoformat() if req["completed_at"] else None,
        "fields": [
            {"id": str(f["id"]), "signer_email": f["signer_email"], "page_number": f["page_number"],
             "x": f["x"], "y": f["y"], "width": f["width"], "height": f["height"],
             "field_type": f["field_type"], "signed": f["signed"],
             "signed_at": f["signed_at"].isoformat() if f["signed_at"] else None}
            for f in fields
        ],
    }


@router.post("/requests", status_code=201)
async def create_request(body: CreateRequest, request: Request,
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    if not body.fields:
        raise HTTPException(status_code=400, detail="At least one signature field is required")
    doc = await _get_doc_or_404(UUID(body.document_id), user_id, db)

    req_id = uuid4()
    await db.execute(
        text("INSERT INTO signature_requests (id, document_id, requester_id, title, message, status) "
             "VALUES (CAST(:id AS uuid), CAST(:doc AS uuid), CAST(:uid AS uuid), :title, :msg, 'pending')"),
        {"id": str(req_id), "doc": str(doc.id), "uid": str(user_id), "title": body.title, "msg": body.message},
    )
    for f in body.fields:
        await db.execute(
            text("INSERT INTO signature_fields (id, request_id, signer_email, page_number, x, y, width, height, field_type) "
                 "VALUES (uuid_generate_v4(), CAST(:rid AS uuid), :email, :page, :x, :y, :w, :h, :ftype)"),
            {"rid": str(req_id), "email": f.signer_email, "page": f.page_number,
             "x": f.x, "y": f.y, "w": f.width, "h": f.height, "ftype": f.field_type},
        )
    await _audit(db, user_id, "signature.requested", doc.id, request)
    await db.flush()
    return await _request_dto(db, req_id)


@router.get("/requests")
async def list_requests(user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    ids = (await db.execute(text(
        "SELECT id FROM signature_requests WHERE requester_id = CAST(:uid AS uuid) ORDER BY created_at DESC"),
        {"uid": str(user_id)})).scalars().all()
    return [await _request_dto(db, rid) for rid in ids]


async def _owned_request(req_id: UUID, user_id: UUID, db: AsyncSession):
    row = (await db.execute(text(
        "SELECT document_id, status FROM signature_requests "
        "WHERE id = CAST(:id AS uuid) AND requester_id = CAST(:uid AS uuid)"),
        {"id": str(req_id), "uid": str(user_id)})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Signature request not found")
    return row


@router.get("/requests/{req_id}")
async def get_request(req_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    await _owned_request(req_id, user_id, db)
    return await _request_dto(db, req_id)


class SignField(BaseModel):
    field_id:         str
    signature_base64: str


@router.post("/requests/{req_id}/sign")
async def sign_field(req_id: UUID, body: SignField, request: Request,
                     user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    row = await _owned_request(req_id, user_id, db)
    if row["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Request is already {row['status']}")

    field = (await db.execute(text(
        "SELECT id, page_number, x, y, width, height, signature FROM signature_fields "
        "WHERE id = CAST(:fid AS uuid) AND request_id = CAST(:rid AS uuid)"),
        {"fid": body.field_id, "rid": str(req_id)})).mappings().first()
    if not field:
        raise HTTPException(status_code=404, detail="Field not found on this request")
    if field["signature"] is not None:
        raise HTTPException(status_code=400, detail="Field already signed")

    img = _decode_png(body.signature_base64)
    doc = await _get_doc_or_404(row["document_id"], user_id, db)
    tmp_in  = f"/tmp/sreq_{req_id}_in.pdf"
    tmp_out = f"/tmp/sreq_{req_id}_out.pdf"
    download_file(doc.s3_key, tmp_in)
    rect = [field["x"], field["y"], field["x"] + field["width"], field["y"] + field["height"]]
    _stamp_image(tmp_in, tmp_out, field["page_number"], rect, img)
    await _save_new_version(doc, tmp_out, user_id, db)

    await db.execute(
        text("UPDATE signature_fields SET signature = :sig, signed_at = NOW() WHERE id = CAST(:fid AS uuid)"),
        {"sig": body.signature_base64, "fid": body.field_id},
    )
    remaining = (await db.execute(text(
        "SELECT count(*) FROM signature_fields WHERE request_id = CAST(:rid AS uuid) AND signature IS NULL"),
        {"rid": str(req_id)})).scalar()
    if remaining == 0:
        await db.execute(text(
            "UPDATE signature_requests SET status='completed', completed_at=NOW(), signed_doc_key=:k "
            "WHERE id = CAST(:rid AS uuid)"), {"k": doc.s3_key, "rid": str(req_id)})

    await _audit(db, user_id, "signature.signed", doc.id, request)
    await db.flush()
    return await _request_dto(db, req_id)

