from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys, os

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_base, "shared"))        # Docker: /app/shared
sys.path.insert(0, os.path.join(_base, "..", "shared"))  # local dev: backend/shared

from shared.database import engine, Base
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="OCR Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1/ocr", tags=["ocr"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ocr"}
