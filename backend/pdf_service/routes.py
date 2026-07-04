"""
PDF Engine: upload, render pages, text/image/shape edits, export, share.
"""
import io
import os
import re
import uuid
import base64
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update, delete, func as sqlfunc, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.audit import record as audit
from shared.malware import scan_bytes, MalwareDetected
from shared.s3 import upload_file, download_file, generate_presigned_url, delete_file
from shared.queue import publish, QUEUES
from models import Document, DocumentVersion, DocumentShare, DocStatus

router = APIRouter()

S3_BUCKET        = os.getenv("S3_BUCKET", "pdf-documents")
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024


# ── Auth dependency (trusts gateway-forwarded header) ─────────────────────────

async def current_user_id(x_user_id: str | None = Header(None)) -> UUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return UUID(x_user_id)


# ── Schemas ───────────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id:            UUID
    filename:      str
    original_name: str
    s3_key:        str
    file_size:     int
    page_count:    int | None
    status:        str
    is_ocr_done:   bool
    is_ai_indexed: bool
    created_at:    datetime

    model_config = {"from_attributes": True}


# PyMuPDF built-in (base-14) font names we expose in the UI. Anything else → Helvetica,
# so an unexpected value can never crash insert_text/insert_textbox.
_BASE14_FONTS = {
    "helv", "helvB", "helvI", "helvBI",   # Helvetica
    "tiro", "tibo", "tiit", "tibi",       # Times
    "cour", "couB", "couI", "couBI",      # Courier
}
def _safe_font(name: str | None) -> str:
    return name if name in _BASE14_FONTS else "helv"


class TextEdit(BaseModel):
    page:     int
    x:        float
    y:        float
    text:     str
    font:     str  = "helv"
    size:     float = 12
    color:    list[float] = [0, 0, 0]  # RGB 0–1


class ImageInsert(BaseModel):
    page:  int
    x:     float
    y:     float
    width: float
    height: float
    base64_image: str


class ShareRequest(BaseModel):
    permission: str = "view"
    expires_hours: int | None = None


class ShareResponse(BaseModel):
    share_token: str
    share_url:   str


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    user_id: UUID = Depends(current_user_id),
    x_user_role: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    data      = await file.read()
    file_size = len(data)

    # ── Validation (do this BEFORE storing anything) ──────────────────────────
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    # Enforce the per-plan storage quota (not just displayed) so a user can't fill the disk.
    plan  = (x_user_role or "free").lower()
    limit = _STORAGE_LIMITS.get(plan, _STORAGE_LIMITS["free"])
    if limit is not None:
        used = await _current_storage_bytes(user_id, db)
        if used + file_size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Storage quota exceeded ({limit // (1024**2)} MB on the {plan} plan). "
                       f"Delete files or upgrade your plan.")
    # Don't trust the client-supplied MIME type — check the real magic bytes.
    if not data[:5].startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="File is not a valid PDF")
    # Malware scan before we ever store the bytes.
    try:
        scan_bytes(data)
    except MalwareDetected as e:
        raise HTTPException(status_code=400, detail=f"File failed the malware scan ({e.signature})")
    try:
        pdf = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=400, detail="Corrupted or unreadable PDF")
    if pdf.is_encrypted:
        pdf.close()
        raise HTTPException(status_code=400, detail="Password-protected PDFs are not supported")
    page_count = len(pdf)
    pdf.close()

    safe_name = f"{uuid.uuid4()}.pdf"
    s3_key    = f"documents/{user_id}/{safe_name}"
    upload_file(s3_key, io.BytesIO(data), content_type="application/pdf")

    doc = Document(
        owner_id=user_id,
        filename=safe_name,
        original_name=file.filename or "document.pdf",
        s3_key=s3_key,
        file_size=file_size,
        page_count=page_count,
        status=DocStatus.processing,
    )
    db.add(doc)
    await db.flush()

    await publish(QUEUES["thumbnail"], {"document_id": str(doc.id), "s3_key": s3_key})
    await publish(QUEUES["ai_index"],  {"document_id": str(doc.id), "s3_key": s3_key, "user_id": str(user_id)})

    doc.status = DocStatus.ready
    return doc


# ── List & CRUD ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    user_id: UUID = Depends(current_user_id),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Document)
        .where(Document.owner_id == user_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return result.scalars().all()


# Per-plan storage allowance (bytes); None = unlimited.
_STORAGE_LIMITS = {
    "free":       100 * 1024**2,   # 100 MB
    "pro":        10  * 1024**3,   # 10 GB
    "business":   100 * 1024**3,   # 100 GB
    "enterprise": None,
    "admin":      None,
}


async def _current_storage_bytes(user_id: UUID, db: AsyncSession) -> int:
    """Total live storage for a user = documents + their version snapshots."""
    docs = (await db.execute(text(
        "SELECT coalesce(sum(file_size), 0) FROM documents "
        "WHERE owner_id = CAST(:u AS uuid) AND deleted_at IS NULL"), {"u": str(user_id)})).scalar()
    versions = (await db.execute(text(
        "SELECT coalesce(sum(v.file_size), 0) FROM document_versions v "
        "JOIN documents d ON d.id = v.document_id "
        "WHERE d.owner_id = CAST(:u AS uuid) AND d.deleted_at IS NULL"), {"u": str(user_id)})).scalar()
    return int(docs or 0) + int(versions or 0)


@router.get("/usage")   # NOTE: must stay declared before /{doc_id}
async def storage_usage(
    user_id: UUID = Depends(current_user_id),
    x_user_role: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Storage + document usage for the current user (dashboard indicator)."""
    doc_count = (await db.execute(text(
        "SELECT count(*) FROM documents "
        "WHERE owner_id = CAST(:u AS uuid) AND deleted_at IS NULL"), {"u": str(user_id)})).scalar()
    used = await _current_storage_bytes(user_id, db)
    plan = (x_user_role or "free").lower()
    limit = _STORAGE_LIMITS.get(plan, _STORAGE_LIMITS["free"])
    return {
        "documents":   int(doc_count or 0),
        "used_bytes":  used,
        "limit_bytes": limit,
        "plan":        plan,
    }


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: UUID, request: Request, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    # Soft delete: mark deleted_at and keep the S3 object for recovery / retention.
    await db.execute(update(Document).where(Document.id == doc_id).values(deleted_at=datetime.now(timezone.utc)))
    await audit(db, action="document.delete", user_id=user_id, resource="document", resource_id=doc_id, request=request)


# ── Download ──────────────────────────────────────────────────────────────────

class DocumentPatch(BaseModel):
    original_name: str | None = None   # rename
    folder_id:     str | None = None   # move; "" / null handled — set to folder or root


@router.patch("/{doc_id}", response_model=DocumentResponse)
async def update_document(doc_id: UUID, body: DocumentPatch, request: Request,
                          user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    fields = body.model_dump(exclude_unset=True)
    if "original_name" in fields and fields["original_name"]:
        await db.execute(update(Document).where(Document.id == doc_id).values(original_name=fields["original_name"]))
    if "folder_id" in fields:
        fid = fields["folder_id"]
        if fid:  # verify the target folder belongs to the caller
            owned = (await db.execute(text(
                "SELECT 1 FROM folders WHERE id = CAST(:f AS uuid) AND owner_id = CAST(:u AS uuid)"),
                {"f": fid, "u": str(user_id)})).first()
            if not owned:
                raise HTTPException(status_code=404, detail="Target folder not found")
        await db.execute(text(
            "UPDATE documents SET folder_id = CAST(:f AS uuid) WHERE id = CAST(:d AS uuid)"),
            {"f": fid, "d": str(doc_id)})
    await audit(db, action="document.updated", user_id=user_id, resource="document", resource_id=doc_id, request=request)
    await db.flush()
    return (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one()


@router.get("/{doc_id}/download")
async def download_document(doc_id: UUID, request: Request, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    url = generate_presigned_url(doc.s3_key, expiry=300)
    await audit(db, action="document.downloaded", user_id=user_id, resource="document", resource_id=doc_id, request=request)
    return {"url": url}


# ── Page Rendering ────────────────────────────────────────────────────────────

@router.get("/{doc_id}/pages/{page_number}")
async def render_page(
    doc_id:      UUID,
    page_number: int,
    zoom:        float = Query(1.5, ge=0.5, le=4.0),
    user_id:     UUID  = Depends(current_user_id),
    db:          AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)

    tmp = f"/tmp/{doc_id}_{page_number}.pdf"
    download_file(doc.s3_key, tmp)

    pdf = fitz.open(tmp)
    if page_number < 1 or page_number > len(pdf):
        pdf.close()
        raise HTTPException(status_code=400, detail=f"page {page_number} out of range")
    page = pdf[page_number - 1]
    mat  = fitz.Matrix(zoom, zoom)
    pix  = page.get_pixmap(matrix=mat)
    img  = pix.tobytes("png")
    pdf.close()

    # cacheable: the viewer busts the URL (reload key) after every edit
    return StreamingResponse(io.BytesIO(img), media_type="image/png",
                             headers={"Cache-Control": "private, max-age=86400"})


# ── Text Extraction ───────────────────────────────────────────────────────────

@router.get("/{doc_id}/text")
async def extract_text(
    doc_id:  UUID,
    page:    int | None = None,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp = f"/tmp/{doc_id}_text.pdf"
    download_file(doc.s3_key, tmp)

    pdf   = fitz.open(tmp)
    pages = [pdf[page - 1]] if page else list(pdf)
    text  = {str(i + 1): p.get_text() for i, p in enumerate(pages)}
    pdf.close()
    return {"text": text}


# ── Edit: Add Text ────────────────────────────────────────────────────────────

@router.post("/{doc_id}/edit/text")
async def add_text(
    doc_id:  UUID,
    body:    TextEdit,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp_in  = f"/tmp/{doc_id}_in.pdf"
    tmp_out = f"/tmp/{doc_id}_out.pdf"
    download_file(doc.s3_key, tmp_in)

    pdf  = fitz.open(tmp_in)
    page = pdf[body.page - 1]
    page.insert_text(
        (body.x, body.y),
        body.text,
        fontname=_safe_font(body.font),
        fontsize=body.size,
        color=tuple(body.color),
    )
    pdf.save(tmp_out)
    pdf.close()

    await _save_new_version(doc, tmp_out, user_id, db)
    return {"message": "Text added"}


# ── Edit: Highlight ───────────────────────────────────────────────────────────

class HighlightEdit(BaseModel):
    page:  int
    quads: list[list[float]]   # list of [x0,y0,x1,y1,x2,y2,x3,y3]
    color: list[float] = [1, 1, 0]


@router.post("/{doc_id}/edit/highlight")
async def add_highlight(
    doc_id:  UUID,
    body:    HighlightEdit,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp_in  = f"/tmp/{doc_id}_in.pdf"
    tmp_out = f"/tmp/{doc_id}_out.pdf"
    download_file(doc.s3_key, tmp_in)

    pdf  = fitz.open(tmp_in)
    page = pdf[body.page - 1]
    for quad in body.quads:
        # fitz.Quad wants 4 points, not 8 flat floats
        points = [fitz.Point(quad[i], quad[i + 1]) for i in range(0, 8, 2)]
        annot = page.add_highlight_annot(fitz.Quad(points))
        annot.set_colors(stroke=body.color)
        annot.update()
    pdf.save(tmp_out)
    pdf.close()

    await _save_new_version(doc, tmp_out, user_id, db)
    return {"message": "Highlights added"}


# ── Edit: Redact ──────────────────────────────────────────────────────────────

class RedactEdit(BaseModel):
    page:  int
    rects: list[list[float]]   # [x0, y0, x1, y1]


@router.post("/{doc_id}/edit/redact")
async def redact(
    doc_id:  UUID,
    body:    RedactEdit,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp_in  = f"/tmp/{doc_id}_in.pdf"
    tmp_out = f"/tmp/{doc_id}_out.pdf"
    download_file(doc.s3_key, tmp_in)

    pdf  = fitz.open(tmp_in)
    page = pdf[body.page - 1]
    for rect in body.rects:
        page.add_redact_annot(fitz.Rect(rect))
    page.apply_redactions()
    pdf.save(tmp_out)
    pdf.close()

    await _save_new_version(doc, tmp_out, user_id, db)
    return {"message": "Redactions applied"}


# ── Edit: Replace text in place ───────────────────────────────────────────────

class ReplaceEdit(BaseModel):
    page:  int
    rect:  list[float]            # [x0, y0, x1, y1] — area of existing text to replace
    text:  str
    font:  str = "helv"
    size:  float | None = None    # auto-fit to the box height when omitted
    color: list[float] = [0, 0, 0]


@router.post("/{doc_id}/edit/replace")
async def replace_text(
    doc_id:  UUID,
    body:    ReplaceEdit,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp_in  = f"/tmp/{doc_id}_in.pdf"
    tmp_out = f"/tmp/{doc_id}_out.pdf"
    download_file(doc.s3_key, tmp_in)

    pdf  = fitz.open(tmp_in)
    page = pdf[body.page - 1]
    rect = fitz.Rect(body.rect)

    # Erase whatever is under the box — pad slightly so glyph ascenders/descenders
    # are fully covered (white fill blends with the page).
    page.add_redact_annot(fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1), fill=(1, 1, 1))
    page.apply_redactions()

    # …then drop the new text on the line's baseline. insert_text (not insert_textbox)
    # has no "must fit the box" constraint, so single-line replacements never silently
    # disappear in a tight box.
    size = body.size or max(7.0, min(12.0, rect.height * 0.85))
    baseline = rect.y1 - max(1.0, rect.height * 0.18)
    page.insert_text((rect.x0, baseline), body.text,
                     fontname=_safe_font(body.font), fontsize=size, color=tuple(body.color))
    pdf.save(tmp_out)
    pdf.close()

    await _save_new_version(doc, tmp_out, user_id, db)
    return {"message": "Text replaced"}


# ── Editable text spans (Smallpdf-style in-place editing) ──────────────────────

@router.get("/{doc_id}/text-spans")
async def text_spans(doc_id: UUID, page: int = Query(1, ge=1),
                     user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    """Every text span on a page with its bbox/size/font/color, so the UI can render
    editable boxes positioned exactly over the original text."""
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp = f"/tmp/{doc_id}_spans.pdf"
    download_file(doc.s3_key, tmp)
    pdf = fitz.open(tmp)
    if page < 1 or page > len(pdf):
        pdf.close(); raise HTTPException(status_code=400, detail=f"page {page} out of range")
    d = pdf[page - 1].get_text("dict")
    spans, i = [], 0
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            for s in line.get("spans", []):
                if not s["text"].strip():
                    continue
                col = s.get("color", 0)
                spans.append({
                    "id": i, "text": s["text"], "bbox": [round(c, 2) for c in s["bbox"]],
                    "size": round(s["size"], 2), "font": s.get("font", ""),
                    "color": [(col >> 16 & 255) / 255, (col >> 8 & 255) / 255, (col & 255) / 255],
                })
                i += 1
    pdf.close()
    return {"page": page, "spans": spans}


# ── Table extraction ──────────────────────────────────────────────────────────

@router.get("/{doc_id}/tables")
async def extract_tables(doc_id: UUID, page: int = Query(1, ge=1),
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp = f"/tmp/{doc_id}_tables.pdf"
    download_file(doc.s3_key, tmp)
    pdf = fitz.open(tmp)
    if page < 1 or page > len(pdf):
        pdf.close(); raise HTTPException(status_code=400, detail=f"page {page} out of range")
    finder = pdf[page - 1].find_tables()
    tables = [{"rows": t.extract()} for t in finder.tables]
    pdf.close()
    return {"page": page, "count": len(tables), "tables": tables}


# ── Edit: Watermark ───────────────────────────────────────────────────────────

class WatermarkEdit(BaseModel):
    text:    str
    opacity: float = 0.15
    size:    float = 48
    color:   list[float] = [0.5, 0.5, 0.5]
    rotate:  int = 45


@router.post("/{doc_id}/edit/watermark")
async def add_watermark(doc_id: UUID, body: WatermarkEdit, request: Request,
                        user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp_in, tmp_out = f"/tmp/{doc_id}_wm_in.pdf", f"/tmp/{doc_id}_wm_out.pdf"
    download_file(doc.s3_key, tmp_in)
    pdf = fitz.open(tmp_in)
    for page in pdf:
        r = page.rect
        pivot = fitz.Point(r.width / 2, r.height / 2)
        mat = fitz.Matrix(1, 1).prerotate(body.rotate)
        page.insert_text(
            fitz.Point(r.width * 0.15, r.height * 0.55),
            body.text, fontsize=body.size, color=tuple(body.color),
            fill_opacity=max(0.02, min(1.0, body.opacity)), morph=(pivot, mat),
        )
    pdf.save(tmp_out)
    pdf.close()
    await _save_new_version(doc, tmp_out, user_id, db)
    await audit(db, action="document.watermark", user_id=user_id, resource="document", resource_id=doc_id, request=request)
    return {"message": "Watermark applied"}


# ── Edit: Shapes ──────────────────────────────────────────────────────────────

class ShapeEdit(BaseModel):
    page:  int
    shape: str                          # rect | line | ellipse | circle | arrow | triangle | polygon
    x0:    float = 0
    y0:    float = 0
    x1:    float = 0
    y1:    float = 0
    points: list[list[float]] | None = None   # for polygon (and optional triangle)
    color: list[float] = [0, 0, 0]
    width: float = 1.5
    fill:  list[float] | None = None


@router.post("/{doc_id}/edit/shape")
async def add_shape(doc_id: UUID, body: ShapeEdit, request: Request,
                    user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp_in, tmp_out = f"/tmp/{doc_id}_si.pdf", f"/tmp/{doc_id}_so.pdf"
    download_file(doc.s3_key, tmp_in)
    pdf  = fitz.open(tmp_in)
    page = pdf[body.page - 1]
    color = tuple(body.color)
    fill  = tuple(body.fill) if body.fill else None
    rect  = fitz.Rect(min(body.x0, body.x1), min(body.y0, body.y1), max(body.x0, body.x1), max(body.y0, body.y1))
    if body.shape == "rect":
        page.draw_rect(rect, color=color, fill=fill, width=body.width)
    elif body.shape in ("ellipse", "circle"):
        page.draw_oval(rect, color=color, fill=fill, width=body.width)
    elif body.shape == "line":
        page.draw_line((body.x0, body.y0), (body.x1, body.y1), color=color, width=body.width)
    elif body.shape == "arrow":
        page.draw_line((body.x0, body.y0), (body.x1, body.y1), color=color, width=body.width)
        # arrowhead at (x1, y1)
        import math
        ang = math.atan2(body.y1 - body.y0, body.x1 - body.x0)
        h = max(8.0, body.width * 4)
        for da in (math.radians(150), math.radians(-150)):
            page.draw_line((body.x1, body.y1),
                           (body.x1 + h * math.cos(ang + da), body.y1 + h * math.sin(ang + da)),
                           color=color, width=body.width)
    elif body.shape == "triangle":
        pts = body.points or [[(body.x0 + body.x1) / 2, body.y0], [body.x0, body.y1], [body.x1, body.y1]]
        page.draw_polyline([tuple(p) for p in pts] + [tuple(pts[0])], color=color, fill=fill, width=body.width)
    elif body.shape == "polygon":
        if not body.points or len(body.points) < 3:
            pdf.close(); raise HTTPException(status_code=400, detail="polygon requires >= 3 points")
        page.draw_polyline([tuple(p) for p in body.points] + [tuple(body.points[0])],
                           color=color, fill=fill, width=body.width)
    else:
        pdf.close()
        raise HTTPException(status_code=400, detail="shape must be rect, line, ellipse, circle, arrow, triangle, or polygon")
    pdf.save(tmp_out)
    pdf.close()
    await _save_new_version(doc, tmp_out, user_id, db)
    await audit(db, action="document.edit_shape", user_id=user_id, resource="document", resource_id=doc_id, request=request)
    return {"message": "Shape added"}


# ── Edit: Insert Image ────────────────────────────────────────────────────────

class ImageEdit(BaseModel):
    page:   int
    image_base64: str
    x:      float
    y:      float
    width:  float = 200
    height: float = 150


@router.post("/{doc_id}/edit/image")
async def add_image(doc_id: UUID, body: ImageEdit, request: Request,
                    user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    try:
        img = base64.b64decode(body.image_base64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image")
    tmp_in, tmp_out = f"/tmp/{doc_id}_ii.pdf", f"/tmp/{doc_id}_io.pdf"
    download_file(doc.s3_key, tmp_in)
    pdf  = fitz.open(tmp_in)
    page = pdf[body.page - 1]
    page.insert_image(fitz.Rect(body.x, body.y, body.x + body.width, body.y + body.height),
                      stream=img, keep_proportion=True)
    pdf.save(tmp_out)
    pdf.close()
    await _save_new_version(doc, tmp_out, user_id, db)
    await audit(db, action="document.edit_image", user_id=user_id, resource="document", resource_id=doc_id, request=request)
    return {"message": "Image inserted"}


# ── Split ─────────────────────────────────────────────────────────────────────

class SplitRequest(BaseModel):
    # 1-indexed inclusive page ranges, e.g. [[1,3],[4,6]]. Omit to split every page.
    ranges: list[list[int]] | None = None


@router.post("/{doc_id}/split", response_model=list[DocumentResponse], status_code=201)
async def split_document(
    doc_id:  UUID,
    body:    SplitRequest,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    tmp = f"/tmp/{doc_id}_split.pdf"
    download_file(doc.s3_key, tmp)

    src   = fitz.open(tmp)
    total = len(src)
    ranges = body.ranges or [[i + 1, i + 1] for i in range(total)]

    # Validate ranges up-front
    for r in ranges:
        if len(r) != 2 or r[0] < 1 or r[1] > total or r[0] > r[1]:
            src.close()
            raise HTTPException(status_code=400, detail=f"Invalid page range {r} (document has {total} pages)")

    created: list[Document] = []
    base = doc.original_name.rsplit(".", 1)[0]
    for idx, (start, end) in enumerate(ranges, 1):
        part = fitz.open()
        part.insert_pdf(src, from_page=start - 1, to_page=end - 1)
        buf = io.BytesIO()
        part.save(buf, garbage=4, deflate=True)
        part.close()
        buf.seek(0)
        size   = buf.getbuffer().nbytes
        s3_key = f"documents/{user_id}/{uuid.uuid4()}_split.pdf"
        upload_file(s3_key, buf, content_type="application/pdf")
        new_doc = Document(
            owner_id=user_id,
            filename=s3_key.split("/")[-1],
            original_name=f"{base}_part{idx}_p{start}-{end}.pdf",
            s3_key=s3_key,
            file_size=size,
            page_count=end - start + 1,
            status=DocStatus.ready,
        )
        db.add(new_doc)
        created.append(new_doc)

    src.close()
    await db.flush()
    return created


# ── Compress ──────────────────────────────────────────────────────────────────

class CompressRequest(BaseModel):
    quality: str = "medium"    # low (smallest) | medium | high (best quality)


# max_side ≈ longest image edge in px (≈ dpi × 11in); jpg_q = JPEG quality
_COMPRESS_PRESETS = {
    "low":    {"max_side": 1100, "jpg_q": 40},
    "medium": {"max_side": 1700, "jpg_q": 60},
    "high":   {"max_side": 2500, "jpg_q": 80},
}


def _recompress_images(pdf: "fitz.Document", max_side: int, jpg_q: int) -> None:
    """Downsample + JPEG-recompress embedded images in place. This is where the real
    savings are for scanned / image-heavy PDFs — structural cleanup barely touches them."""
    from PIL import Image
    seen: set[int] = set()
    for page in pdf:
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                base = pdf.extract_image(xref)
                data = base["image"]
                pil = Image.open(io.BytesIO(data))
                if max(pil.size) > max_side:
                    pil.thumbnail((max_side, max_side))
                if pil.mode not in ("RGB", "L"):
                    pil = pil.convert("RGB")
                buf = io.BytesIO()
                pil.save(buf, "JPEG", quality=jpg_q, optimize=True)
                if buf.getbuffer().nbytes < len(data):   # only replace when it actually shrinks
                    page.replace_image(xref, stream=buf.getvalue())
            except Exception:
                continue   # unsupported image type → leave it untouched


@router.post("/{doc_id}/compress")
async def compress_document(
    doc_id:  UUID,
    body:    CompressRequest | None = None,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    quality = (body.quality if body else "medium").lower()
    preset = _COMPRESS_PRESETS.get(quality)
    if not preset:
        raise HTTPException(status_code=400, detail="quality must be low, medium or high")

    doc = await _get_doc_or_404(doc_id, user_id, db)
    original_size = doc.file_size
    tmp_in  = f"/tmp/{doc_id}_cin.pdf"
    tmp_out = f"/tmp/{doc_id}_cout.pdf"
    download_file(doc.s3_key, tmp_in)

    pdf = fitz.open(tmp_in)
    _recompress_images(pdf, preset["max_side"], preset["jpg_q"])
    # garbage=4 dedupes/removes unused objects; deflate compresses streams;
    # clean rewrites a tidy, smaller file.
    pdf.save(tmp_out, garbage=4, deflate=True, clean=True)
    pdf.close()

    await _save_new_version(doc, tmp_out, user_id, db)
    await db.refresh(doc)
    resp = DocumentResponse.model_validate(doc).model_dump()
    resp.update({
        "original_size":   original_size,
        "compressed_size": doc.file_size,
        "saved_ratio":     round(1 - doc.file_size / original_size, 3) if original_size else 0.0,
        "quality":         quality,
    })
    return resp


# ── Merge ─────────────────────────────────────────────────────────────────────

class MergeRequest(BaseModel):
    document_ids: list[UUID]


@router.post("/merge", response_model=DocumentResponse, status_code=201)
async def merge_documents(
    body:    MergeRequest,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    merged = fitz.open()
    for did in body.document_ids:
        doc = await _get_doc_or_404(did, user_id, db)
        tmp = f"/tmp/merge_{did}.pdf"
        download_file(doc.s3_key, tmp)
        src = fitz.open(tmp)
        merged.insert_pdf(src)
        src.close()

    buf = io.BytesIO()
    merged.save(buf)
    pages = len(merged)
    merged.close()
    size = buf.getbuffer().nbytes      # capture BEFORE upload (upload closes the buffer)
    buf.seek(0)

    s3_key = f"documents/{user_id}/{uuid.uuid4()}_merged.pdf"
    upload_file(s3_key, buf)

    new_doc = Document(
        owner_id=user_id,
        filename=s3_key.split("/")[-1],
        original_name="merged.pdf",
        s3_key=s3_key,
        file_size=size,
        page_count=pages,
        status=DocStatus.ready,
    )
    db.add(new_doc)
    await db.flush()
    return new_doc


# ── Share ─────────────────────────────────────────────────────────────────────

@router.post("/{doc_id}/share", response_model=ShareResponse)
async def share_document(
    doc_id:  UUID,
    body:    ShareRequest,
    request: Request,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    token = secrets.token_urlsafe(32)
    expires = None
    if body.expires_hours:
        expires = datetime.now(timezone.utc) + timedelta(hours=body.expires_hours)

    share = DocumentShare(
        document_id=doc.id,
        share_token=token,
        permission=body.permission,
        expires_at=expires,
        created_by=user_id,
    )
    db.add(share)
    await audit(db, action="document.share", user_id=user_id, resource="document", resource_id=doc.id,
                request=request, metadata={"permission": body.permission})
    base_url = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")
    return ShareResponse(share_token=token, share_url=f"{base_url}/shared/{token}")


# ── Versions ──────────────────────────────────────────────────────────────────

@router.get("/{doc_id}/versions")
async def list_versions(
    doc_id:  UUID,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    await _get_doc_or_404(doc_id, user_id, db)
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.version.desc())
    )
    versions = result.scalars().all()
    return [{"version": v.version, "file_size": v.file_size, "created_at": v.created_at, "comment": v.comment} for v in versions]


@router.post("/{doc_id}/versions/{version}/restore")
async def restore_version(
    doc_id:  UUID,
    version: int,
    user_id: UUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc_id,
            DocumentVersion.version == version,
        )
    )
    ver = result.scalar_one_or_none()
    if not ver:
        raise HTTPException(status_code=404, detail="Version not found")

    await db.execute(update(Document).where(Document.id == doc_id).values(
        s3_key=ver.s3_key, file_size=ver.file_size, page_count=_page_count_of(ver.s3_key)))
    return {"message": f"Restored to version {version}"}


@router.post("/{doc_id}/undo")
async def undo_edit(doc_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    """Step one edit backward. On the first undo we snapshot the live state as a
    version row so a later redo can return to it."""
    doc = await _get_doc_or_404(doc_id, user_id, db)
    await _lock_document(doc_id, db)
    versions = await _ordered_versions(doc_id, db)
    keys = [v.s3_key for v in versions]
    if doc.s3_key not in keys:
        max_ver = max((v.version for v in versions), default=0)
        db.add(DocumentVersion(document_id=doc_id, version=max_ver + 1,
                               s3_key=doc.s3_key, file_size=doc.file_size, created_by=user_id))
        await db.flush()
        versions = await _ordered_versions(doc_id, db)
        keys = [v.s3_key for v in versions]
    idx = keys.index(doc.s3_key)
    if idx <= 0:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    tgt = versions[idx - 1]
    await db.execute(update(Document).where(Document.id == doc_id).values(
        s3_key=tgt.s3_key, file_size=tgt.file_size, page_count=_page_count_of(tgt.s3_key)))
    await db.commit()   # see _save_new_version — avoid the response-before-commit race
    return {"message": "Undone", "version": tgt.version}


@router.post("/{doc_id}/redo")
async def redo_edit(doc_id: UUID, user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    """Step one edit forward through the version timeline."""
    doc = await _get_doc_or_404(doc_id, user_id, db)
    versions = await _ordered_versions(doc_id, db)
    keys = [v.s3_key for v in versions]
    if doc.s3_key not in keys:
        raise HTTPException(status_code=400, detail="Nothing to redo")
    idx = keys.index(doc.s3_key)
    if idx >= len(versions) - 1:
        raise HTTPException(status_code=400, detail="Nothing to redo")
    tgt = versions[idx + 1]
    await db.execute(update(Document).where(Document.id == doc_id).values(
        s3_key=tgt.s3_key, file_size=tgt.file_size, page_count=_page_count_of(tgt.s3_key)))
    await db.commit()
    return {"message": "Redone", "version": tgt.version}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_doc_or_404(doc_id: UUID, user_id: UUID, db: AsyncSession) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == doc_id, Document.owner_id == user_id, Document.deleted_at.is_(None))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


async def _ordered_versions(doc_id: UUID, db: AsyncSession) -> list[DocumentVersion]:
    return list((await db.execute(
        select(DocumentVersion).where(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.version.asc())
    )).scalars().all())


def _page_count_of(s3_key: str) -> int:
    tmp = f"/tmp/pc_{uuid.uuid4()}.pdf"
    download_file(s3_key, tmp)
    with fitz.open(tmp) as pdf:
        return len(pdf)


async def _lock_document(doc_id: UUID, db: AsyncSession) -> None:
    """Serialise version-row writes for one document. Rapid successive edits (and
    Ctrl+Z right after) otherwise read the same max(version) and collide on the
    (document_id, version) unique constraint. Transaction-scoped → auto-released on commit."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": str(doc_id)})


async def _save_new_version(doc: Document, tmp_out_path: str, user_id: UUID, db: AsyncSession) -> None:
    """Append a new edit to the document's linear history.

    Each version row snapshots a *distinct* state (by s3_key); ``doc.s3_key`` is the
    live/current state. Normally we snapshot the pre-edit live state, then move the
    document onto a freshly-written key. If the user is editing from an *undone*
    state (the current key is already a version row), we truncate the now-invalid
    redo-future first so the timeline stays linear.
    """
    await _lock_document(doc.id, db)
    versions = await _ordered_versions(doc.id, db)
    keys = [v.s3_key for v in versions]
    new_size = os.path.getsize(tmp_out_path)
    # strip any previous suffix so keys don't grow unboundedly (…_v2_v3_v4.pdf)
    base_key = re.sub(r"(_v\d+)+\.pdf$", ".pdf", doc.s3_key)

    if doc.s3_key in keys:
        # editing from a restored/undone state → drop the redo branch after the cursor
        cur = keys.index(doc.s3_key)
        cur_ver = versions[cur].version
        await db.execute(delete(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.version > cur_ver))
        base_ver = cur_ver   # current state is already a version row; don't re-snapshot
    else:
        # normal edit → snapshot the current (pre-edit) live state
        max_ver = max((v.version for v in versions), default=0)
        db.add(DocumentVersion(
            document_id=doc.id, version=max_ver + 1,
            s3_key=doc.s3_key, file_size=doc.file_size, created_by=user_id))
        base_ver = max_ver + 1

    new_key = base_key.replace(".pdf", f"_v{base_ver + 1}.pdf")
    with open(tmp_out_path, "rb") as f:
        upload_file(new_key, f)

    # page ops (add/delete/duplicate/…) change the count — keep the DB in sync or
    # the viewer renders the wrong number of pages
    with fitz.open(tmp_out_path) as _pdf:
        new_pages = len(_pdf)

    await db.execute(
        update(Document).where(Document.id == doc.id)
        .values(s3_key=new_key, file_size=new_size, page_count=new_pages)
    )
    # Commit NOW, not in the dependency teardown (which runs after the response is
    # sent) — otherwise an immediate follow-up request (e.g. Ctrl+Z right after an
    # edit) races the uncommitted version rows and can hit the unique constraint.
    await db.commit()
