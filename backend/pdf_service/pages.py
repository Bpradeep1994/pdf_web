"""
Page tools (PDFForge Phase 4/5): rotate, delete, reorder, duplicate, extract pages.
Operates with PyMuPDF; in-place edits save a new version, extract creates a new document.
Mounted at /api/v1/documents so paths are /documents/{id}/pages/...
"""
import io
import uuid
from uuid import UUID

import fitz
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.s3 import download_file, upload_file
from models import Document, DocStatus
from routes import current_user_id, _get_doc_or_404, _save_new_version

router = APIRouter()


class RotatePages(BaseModel):
    pages: list[int] = []        # 1-indexed; empty = all pages
    degrees: int = 90            # 90 | 180 | 270


class PageList(BaseModel):
    pages: list[int]             # 1-indexed


class Reorder(BaseModel):
    order: list[int]             # full 1-indexed permutation


def _open(doc_s3_key: str, tag: str):
    tmp = f"/tmp/pg_{uuid.uuid4()}_{tag}.pdf"
    download_file(doc_s3_key, tmp)
    return fitz.open(tmp)


class AddPage(BaseModel):
    after: int | None = None     # 1-indexed page to insert after; 0 = at start; None = at end


@router.post("/{doc_id}/pages/add")
async def add_page(doc_id: UUID, body: AddPage,
                   user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    """Insert a blank page (sized like its neighbour) after the given page."""
    doc = await _get_doc_or_404(doc_id, user_id, db)
    pdf = _open(doc.s3_key, "add")
    n = len(pdf)
    after = n if body.after is None else body.after
    if after < 0 or after > n:
        pdf.close(); raise HTTPException(status_code=400, detail=f"after must be 0..{n}")
    ref = pdf[min(max(after, 1), n) - 1].rect   # neighbour's size
    pdf.new_page(pno=after, width=ref.width, height=ref.height)
    out = f"/tmp/pg_{doc_id}_add_out.pdf"; pdf.save(out); pdf.close()
    await _save_new_version(doc, out, user_id, db)
    return {"message": "Page added", "page_count": n + 1}


@router.post("/{doc_id}/pages/rotate")
async def rotate_pages(doc_id: UUID, body: RotatePages,
                       user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    if body.degrees % 90 != 0:
        raise HTTPException(status_code=400, detail="degrees must be a multiple of 90")
    doc = await _get_doc_or_404(doc_id, user_id, db)
    pdf = _open(doc.s3_key, "rot")
    targets = body.pages or list(range(1, len(pdf) + 1))
    for p in targets:
        if p < 1 or p > len(pdf):
            pdf.close(); raise HTTPException(status_code=400, detail=f"page {p} out of range")
        page = pdf[p - 1]
        page.set_rotation((page.rotation + body.degrees) % 360)
    out = f"/tmp/pg_{doc_id}_rot_out.pdf"; pdf.save(out); pdf.close()
    await _save_new_version(doc, out, user_id, db)
    return {"message": "Pages rotated", "pages": targets}


@router.post("/{doc_id}/pages/delete")
async def delete_pages(doc_id: UUID, body: PageList,
                       user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    pdf = _open(doc.s3_key, "del")
    if len(body.pages) >= len(pdf):
        pdf.close(); raise HTTPException(status_code=400, detail="cannot delete all pages")
    for p in sorted(set(body.pages), reverse=True):
        if p < 1 or p > len(pdf):
            pdf.close(); raise HTTPException(status_code=400, detail=f"page {p} out of range")
        pdf.delete_page(p - 1)
    out = f"/tmp/pg_{doc_id}_del_out.pdf"; pdf.save(out); pdf.close()
    await _save_new_version(doc, out, user_id, db)
    return {"message": "Pages deleted"}


@router.post("/{doc_id}/pages/reorder")
async def reorder_pages(doc_id: UUID, body: Reorder,
                        user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    pdf = _open(doc.s3_key, "ord")
    n = len(pdf)
    if sorted(body.order) != list(range(1, n + 1)):
        pdf.close(); raise HTTPException(status_code=400, detail=f"order must be a permutation of 1..{n}")
    pdf.select([p - 1 for p in body.order])
    out = f"/tmp/pg_{doc_id}_ord_out.pdf"; pdf.save(out); pdf.close()
    await _save_new_version(doc, out, user_id, db)
    return {"message": "Pages reordered"}


@router.post("/{doc_id}/pages/duplicate")
async def duplicate_page(doc_id: UUID, body: PageList,
                         user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    pdf = _open(doc.s3_key, "dup")
    n = len(pdf)
    for p in body.pages:
        if p < 1 or p > n:
            pdf.close(); raise HTTPException(status_code=400, detail=f"page {p} out of range")
    # fullcopy_page is broken in this PyMuPDF build; copy from a second handle instead.
    # Process descending so each insert position stays valid as the doc grows.
    src = _open(doc.s3_key, "dupsrc")
    for p in sorted(set(body.pages), reverse=True):
        pdf.insert_pdf(src, from_page=p - 1, to_page=p - 1, start_at=p)
    src.close()
    out = f"/tmp/pg_{doc_id}_dup_out.pdf"; pdf.save(out); pdf.close()
    await _save_new_version(doc, out, user_id, db)
    return {"message": "Pages duplicated"}


class ReplacePage(BaseModel):
    page:               int    # 1-indexed target page in this document
    source_document_id: str
    source_page:        int    # 1-indexed page in the source document


@router.post("/{doc_id}/pages/replace")
async def replace_page(doc_id: UUID, body: ReplacePage,
                       user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    src_doc = await _get_doc_or_404(UUID(body.source_document_id), user_id, db)
    pdf = _open(doc.s3_key, "rep")
    src = _open(src_doc.s3_key, "reps")
    if body.page < 1 or body.page > len(pdf):
        pdf.close(); src.close(); raise HTTPException(status_code=400, detail="target page out of range")
    if body.source_page < 1 or body.source_page > len(src):
        pdf.close(); src.close(); raise HTTPException(status_code=400, detail="source page out of range")
    # remove the target page, then splice the source page in at that position
    pdf.delete_page(body.page - 1)
    pdf.insert_pdf(src, from_page=body.source_page - 1, to_page=body.source_page - 1, start_at=body.page - 1)
    src.close()
    out = f"/tmp/pg_{doc_id}_rep_out.pdf"; pdf.save(out); pdf.close()
    await _save_new_version(doc, out, user_id, db)
    return {"message": "Page replaced"}


@router.post("/{doc_id}/pages/extract", status_code=201)
async def extract_pages(doc_id: UUID, body: PageList,
                        user_id: UUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    doc = await _get_doc_or_404(doc_id, user_id, db)
    src = _open(doc.s3_key, "ext")
    for p in body.pages:
        if p < 1 or p > len(src):
            src.close(); raise HTTPException(status_code=400, detail=f"page {p} out of range")
    out_pdf = fitz.open()
    for p in body.pages:
        out_pdf.insert_pdf(src, from_page=p - 1, to_page=p - 1)
    buf = io.BytesIO(); out_pdf.save(buf); size = buf.getbuffer().nbytes; pages = len(out_pdf)
    out_pdf.close(); src.close(); buf.seek(0)

    s3_key = f"documents/{user_id}/{uuid.uuid4()}_extract.pdf"
    upload_file(s3_key, buf, content_type="application/pdf")
    new_doc = Document(
        owner_id=user_id, filename=s3_key.split("/")[-1],
        original_name=doc.original_name.rsplit(".", 1)[0] + "_extract.pdf",
        s3_key=s3_key, file_size=size, page_count=pages, status=DocStatus.ready)
    db.add(new_doc)
    await db.flush()
    return {"id": str(new_doc.id), "page_count": pages}
