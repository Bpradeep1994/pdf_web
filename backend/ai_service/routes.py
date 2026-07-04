"""
AI Engine: RAG pipeline, chat with PDF, summarize, translate, contract analysis.
Vector store: Qdrant. LLM: OpenAI or Anthropic (configurable).
"""
import io
import os
import uuid
import hashlib
import random
from datetime import datetime, timezone
from uuid import UUID as PyUUID

import fitz
import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.s3 import download_file
from models import AISession, AIMessage, Document

router = APIRouter()

QDRANT_URL      = os.getenv("QDRANT_URL",       "http://localhost:6333")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY",   "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY",   "")
LLM_PROVIDER    = os.getenv("LLM_PROVIDER",     "openai")   # openai | anthropic | gemini
LLM_MODEL       = os.getenv("LLM_MODEL",        "gpt-4o")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL",     "gemini-1.5-flash")
EMBED_MODEL     = os.getenv("EMBEDDING_MODEL",  "text-embedding-3-small")
COLLECTION      = "pdf_chunks"
CHUNK_SIZE      = 800
CHUNK_OVERLAP   = 150
TOP_K           = 5
EMBED_DIM       = 1536

STUB_MODE = not (OPENAI_API_KEY or ANTHROPIC_KEY or GEMINI_API_KEY)


# ── Auth ──────────────────────────────────────────────────────────────────────

async def current_user_id(x_user_id: str | None = Header(None)) -> PyUUID:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return PyUUID(x_user_id)


# ── Qdrant client ─────────────────────────────────────────────────────────────

_qdrant: AsyncQdrantClient | None = None


async def get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(url=QDRANT_URL)
        collections = await _qdrant.get_collections()
        names = [c.name for c in collections.collections]
        if COLLECTION not in names:
            await _qdrant.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
    return _qdrant


# ── Embedding ─────────────────────────────────────────────────────────────────

def _stub_embed(text: str) -> list[float]:
    # Deterministic pseudo-embedding so the same text always maps to the same vector
    # → RAG retrieval is meaningful offline / without API keys (demo + tests).
    seed = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rng  = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(EMBED_DIM)]


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if STUB_MODE:
        return [_stub_embed(t) for t in texts]
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": EMBED_MODEL, "input": texts},
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


# ── Schemas ───────────────────────────────────────────────────────────────────

class IndexRequest(BaseModel):
    document_id: str
    s3_key:      str
    user_id:     str


class ChatRequest(BaseModel):
    message:     str
    document_id: str | None = None
    session_id:  str | None = None


class ChatResponse(BaseModel):
    answer:     str
    session_id: str
    sources:    list[dict]


class SummarizeRequest(BaseModel):
    document_id: str
    style:       str = "brief"   # brief | detailed | bullet


class TranslateRequest(BaseModel):
    document_id: str
    target_lang: str


class AnalyzeRequest(BaseModel):
    document_id: str
    analysis_type: str   # contract | resume | invoice | general


# ── Index Pipeline (called by worker after upload) ────────────────────────────

@router.post("/index", status_code=202)
async def index_document(body: IndexRequest, qdrant: AsyncQdrantClient = Depends(get_qdrant)):
    tmp = f"/tmp/ai_{body.document_id}.pdf"
    download_file(body.s3_key, tmp)

    pdf   = fitz.open(tmp)
    pages = [page.get_text() for page in pdf]
    pdf.close()

    full_text = " ".join(pages)
    chunks    = _chunk_text(full_text)
    if not chunks:
        return {"message": "No text to index"}

    embeddings = await embed_texts(chunks)
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "document_id": body.document_id,
                "user_id":     body.user_id,
                "chunk_index": i,
                "text":        chunks[i],
                "page":        _chunk_page(i, len(pages), len(chunks)),
            },
        )
        for i, emb in enumerate(embeddings)
    ]
    await qdrant.upsert(collection_name=COLLECTION, points=points)
    return {"message": "Indexed", "chunks": len(chunks)}


def _chunk_page(chunk_idx: int, pages: int, total_chunks: int) -> int:
    return max(1, round(chunk_idx / total_chunks * pages) + 1)


# ── Chat with PDF ─────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    body:    ChatRequest,
    user_id: PyUUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
    qdrant:  AsyncQdrantClient = Depends(get_qdrant),
):
    session_id = body.session_id
    if not session_id:
        session = AISession(user_id=user_id, document_id=PyUUID(body.document_id) if body.document_id else None)
        db.add(session)
        await db.flush()
        session_id = str(session.id)

    query_embedding = (await embed_texts([body.message]))[0]

    filters = None
    if body.document_id:
        filters = Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=body.document_id))])

    search_result = await qdrant.search(
        collection_name=COLLECTION,
        query_vector=query_embedding,
        query_filter=filters,
        limit=TOP_K,
    )

    context_chunks = [hit.payload["text"] for hit in search_result]
    sources        = [{"text": hit.payload["text"][:200], "page": hit.payload.get("page"), "score": hit.score} for hit in search_result]

    history = await _load_history(PyUUID(session_id), db)
    answer  = await _call_llm(body.message, context_chunks, history)

    db.add(AIMessage(session_id=PyUUID(session_id), role="user",      content=body.message))
    db.add(AIMessage(session_id=PyUUID(session_id), role="assistant", content=answer))

    return ChatResponse(answer=answer, session_id=session_id, sources=sources)


# ── Summarize ─────────────────────────────────────────────────────────────────

@router.post("/summarize")
async def summarize(
    body:    SummarizeRequest,
    user_id: PyUUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    text = await _get_document_text(body.document_id, user_id, db)

    prompts = {
        "brief":    f"Summarize this document in 2-3 sentences:\n\n{text[:4000]}",
        "detailed": f"Provide a detailed summary with key points:\n\n{text[:8000]}",
        "bullet":   f"Summarize this document as bullet points:\n\n{text[:6000]}",
    }
    prompt  = prompts.get(body.style, prompts["brief"])
    summary = await _call_llm_simple(prompt)
    return {"summary": summary}


# ── Translate ─────────────────────────────────────────────────────────────────

@router.post("/translate")
async def translate(
    body:    TranslateRequest,
    user_id: PyUUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    text       = await _get_document_text(body.document_id, user_id, db)
    prompt     = f"Translate the following text to {body.target_lang}:\n\n{text[:6000]}"
    translated = await _call_llm_simple(prompt)
    return {"translated_text": translated, "target_language": body.target_lang}


# ── Document Analysis ─────────────────────────────────────────────────────────

ANALYSIS_PROMPTS = {
    "contract":     "Analyze this contract. Identify: parties, key obligations, risks, termination clauses, penalties.",
    "resume":       "Analyze this resume. Extract: candidate name, skills, experience, education, key achievements.",
    "invoice":      "Analyze this invoice. Extract: vendor, buyer, items, amounts, tax, total, due date.",
    "requirements": "Extract all explicit and implicit requirements from this document as a numbered list, grouped by functional and non-functional.",
    "general":      "Analyze this document and extract key information, entities, dates, and actionable items.",
}


@router.post("/analyze")
async def analyze(
    body:    AnalyzeRequest,
    user_id: PyUUID = Depends(current_user_id),
    db:      AsyncSession = Depends(get_db),
):
    text       = await _get_document_text(body.document_id, user_id, db)
    instruction = ANALYSIS_PROMPTS.get(body.analysis_type, ANALYSIS_PROMPTS["general"])
    prompt      = f"{instruction}\n\nDocument:\n{text[:8000]}"
    result      = await _call_llm_simple(prompt)
    return {"analysis": result, "type": body.analysis_type}


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(user_id: PyUUID = Depends(current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AISession)
        .where(AISession.user_id == user_id)
        .order_by(AISession.updated_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: PyUUID,
    user_id:    PyUUID = Depends(current_user_id),
    db:         AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIMessage)
        .where(AIMessage.session_id == session_id)
        .order_by(AIMessage.created_at.asc())
    )
    return result.scalars().all()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_document_text(doc_id: str, user_id: PyUUID, db: AsyncSession) -> str:
    result = await db.execute(
        select(Document).where(Document.id == PyUUID(doc_id), Document.owner_id == user_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    tmp = f"/tmp/ai_read_{doc_id}.pdf"
    download_file(doc.s3_key, tmp)
    pdf  = fitz.open(tmp)
    text = " ".join(page.get_text() for page in pdf)
    pdf.close()
    return text


async def _load_history(session_id: PyUUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(AIMessage)
        .where(AIMessage.session_id == session_id)
        .order_by(AIMessage.created_at.asc())
        .limit(20)
    )
    return [{"role": m.role, "content": m.content} for m in result.scalars()]


async def _dispatch(system: str, messages: list[dict]) -> str:
    if LLM_PROVIDER == "anthropic":
        return await _call_anthropic(system, messages)
    if LLM_PROVIDER == "gemini":
        return await _call_gemini(system, messages)
    return await _call_openai(system, messages)


async def _call_llm(question: str, context: list[str], history: list[dict]) -> str:
    context_str = "\n\n".join(context)
    system      = f"You are a helpful AI assistant for a PDF editor. Answer questions based on the document context provided.\n\nContext:\n{context_str}"
    messages    = history + [{"role": "user", "content": question}]
    return await _dispatch(system, messages)


async def _call_llm_simple(prompt: str) -> str:
    return await _dispatch("You are a helpful document AI assistant.", [{"role": "user", "content": prompt}])


async def _call_openai(system: str, messages: list[dict]) -> str:
    if STUB_MODE:
        return f"[AI stub] Received: {messages[-1]['content'][:200]}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": LLM_MODEL, "messages": [{"role": "system", "content": system}] + messages},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _call_anthropic(system: str, messages: list[dict]) -> str:
    if STUB_MODE:
        return f"[AI stub] Received: {messages[-1]['content'][:200]}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
            json={"model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                  "max_tokens": 2048, "system": system, "messages": messages},
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


async def _call_gemini(system: str, messages: list[dict]) -> str:
    if STUB_MODE:
        return f"[AI stub] Received: {messages[-1]['content'][:200]}"
    # Map chat roles to Gemini's (user|model) and pass the system prompt separately.
    contents = [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in messages
    ]
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={"systemInstruction": {"parts": [{"text": system}]}, "contents": contents},
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
