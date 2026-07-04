from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys, os

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_base, "shared"))
sys.path.insert(0, os.path.join(_base, "..", "shared"))

from shared.database import engine, Base
from shared.s3 import StorageUnavailable
from routes import router
from esign import router as esign_router
from projects import router as projects_router
from folders import router as folders_router
from pages import router as pages_router
from comments import router as comments_router
from annotations import router as annotations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="PDF Service", version="1.0.0", lifespan=lifespan)


@app.exception_handler(StorageUnavailable)
async def _storage_unavailable(request: Request, exc: StorageUnavailable):
    # object storage down → fast, clean 503 instead of a hung worker / 500
    return JSONResponse(status_code=503, content={"detail": "Storage temporarily unavailable — try again shortly"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(esign_router, prefix="/api/v1/signatures", tags=["signatures"])
app.include_router(projects_router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(folders_router, prefix="/api/v1/folders", tags=["folders"])
app.include_router(pages_router, prefix="/api/v1/documents", tags=["pages"])
app.include_router(comments_router, prefix="/api/v1/documents", tags=["comments"])
app.include_router(annotations_router, prefix="/api/v1/documents", tags=["annotations"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "pdf"}
