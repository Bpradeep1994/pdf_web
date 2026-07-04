from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import sys, os

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_base, "shared"))
sys.path.insert(0, os.path.join(_base, "..", "shared"))

from routes import router
from shared.s3 import StorageUnavailable


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Conversion Service", version="1.0.0", lifespan=lifespan)


@app.exception_handler(StorageUnavailable)
async def _storage_unavailable(request: Request, exc: StorageUnavailable):
    return JSONResponse(status_code=503, content={"detail": "Storage temporarily unavailable — try again shortly"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1/convert", tags=["conversion"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "conversion"}
