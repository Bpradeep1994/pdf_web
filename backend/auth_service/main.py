from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sys, os

_base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_base, "shared"))
sys.path.insert(0, os.path.join(_base, "..", "shared"))

from shared.database import engine, Base
from routes import router, internal_router
from admin import admin_router, support_router, analytics_router
from billing import billing_router
from notifications import notifications_router
from api_keys import keys_router, keys_internal_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Auth Service", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(support_router, prefix="/api/v1/support", tags=["support"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(billing_router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(keys_router, prefix="/api/v1/keys", tags=["api-keys"])
app.include_router(internal_router, prefix="/internal", tags=["internal"])
app.include_router(keys_internal_router, prefix="/internal", tags=["internal"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth"}
