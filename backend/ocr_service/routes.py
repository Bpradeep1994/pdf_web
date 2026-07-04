"""
OCR Service: image extraction -> text recognition -> searchable/editable PDF.
Uses PaddleOCR with Tesseract as fallback.
"""
import io
import os
import uuid
from uuid import UUID

import fitz
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.s3 import download_file, upload_file
from models import Document

router = APIRouter()

USE_PADDLE = os.getenv("USE_PADDLE_OCR", "true").lower() == "true"


async def current_user_id(x_user_id: str | None = Header(None)) -> UUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return UUID(x_user_id)


class OCRRequest(BaseModel):
    document_id: str
    s3_key:      str
    language:    str = "en"


class OCRResponse(BaseModel):
    document_id: str
    pages:       dict[str, str]
    output_key:  str


@router.post("/process", response_model=OCRResponse)
async def process_ocr(body: OCRRequest, user_id: UUID = Depends(current_user_id)):
    tmp_in  = f"/tmp/ocr_{body.document_id}_in.pdf"
    tmp_out = f"/tmp/ocr_{body.document_id}_out.pdf"
    download_file(body.s3_key, tmp_in)

    page_texts: dict[str, str] = {}

    if USE_PADDLE:
        page_texts = _paddle_ocr(tmp_in)
    else:
        page_texts = _tesseract_ocr(tmp_in, body.language)

    output_key = _create_searchable_pdf(tmp_in, tmp_out, page_texts)
    return OCRResponse(document_id=body.document_id, pages=page_texts, output_key=output_key)


@router.get("/status/{document_id}")
async def ocr_status(document_id: str, db: AsyncSession = Depends(get_db)):
    from models import Document
    result = await db.execute(select(Document).where(Document.id == UUID(document_id)))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"document_id": document_id, "is_ocr_done": doc.is_ocr_done}


# ── OCR Engines ───────────────────────────────────────────────────────────────

def _paddle_ocr(pdf_path: str) -> dict[str, str]:
    try:
        from paddleocr import PaddleOCR
        import numpy as np
        from PIL import Image

        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        pdf = fitz.open(pdf_path)
        texts: dict[str, str] = {}

        for i, page in enumerate(pdf):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            arr = np.array(img)
            result = ocr.ocr(arr, cls=True)
            page_text = " ".join(
                line[1][0] for block in (result or []) for line in (block or [])
            )
            texts[str(i + 1)] = page_text

        pdf.close()
        return texts
    except ImportError:
        return _tesseract_ocr(pdf_path, "eng")


def _tesseract_ocr(pdf_path: str, language: str = "eng") -> dict[str, str]:
    import pytesseract
    from PIL import Image

    pdf   = fitz.open(pdf_path)
    texts: dict[str, str] = {}

    for i, page in enumerate(pdf):
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text = pytesseract.image_to_string(img, lang=language)
        texts[str(i + 1)] = text

    pdf.close()
    return texts


def _create_searchable_pdf(src_path: str, out_path: str, page_texts: dict[str, str]) -> str:
    pdf = fitz.open(src_path)
    for i, page in enumerate(pdf):
        text = page_texts.get(str(i + 1), "")
        if text.strip():
            page.insert_text(
                (0, 0),
                text,
                fontsize=0.1,
                color=(1, 1, 1),
                overlay=False,
            )
    pdf.save(out_path)
    pdf.close()

    output_key = src_path.replace("_in.pdf", "_ocr.pdf").replace("/tmp/", "ocr/")
    with open(out_path, "rb") as f:
        upload_file(output_key, f)
    return output_key
