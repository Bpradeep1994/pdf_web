"""
API Gateway — single entry point for all frontend traffic.
Routes requests to downstream microservices, handles auth validation,
rate limiting, and request logging.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.requests import ClientDisconnect
import httpx
import redis.asyncio as aioredis
from prometheus_fastapi_instrumentator import Instrumentator
import asyncio
import json
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("gateway")

AUTH_SERVICE_URL       = os.getenv("AUTH_SERVICE_URL",       "http://localhost:8001")
PDF_SERVICE_URL        = os.getenv("PDF_SERVICE_URL",        "http://localhost:8002")
AI_SERVICE_URL         = os.getenv("AI_SERVICE_URL",         "http://localhost:8003")
OCR_SERVICE_URL        = os.getenv("OCR_SERVICE_URL",        "http://localhost:8004")
CONVERSION_SERVICE_URL = os.getenv("CONVERSION_SERVICE_URL", "http://localhost:8005")
REDIS_URL              = os.getenv("REDIS_URL",              "redis://localhost:6379/0")

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", 100))
RATE_LIMIT_WINDOW   = int(os.getenv("RATE_LIMIT_WINDOW",   60))
# Trusted bypass for CI/test runs. Unset in production → bypass impossible.
RATE_LIMIT_BYPASS_TOKEN = os.getenv("RATE_LIMIT_BYPASS_TOKEN", "")

SERVICE_MAP: dict[str, str] = {
    "/api/v1/auth":       AUTH_SERVICE_URL,
    "/api/v1/admin":      AUTH_SERVICE_URL,
    "/api/v1/billing":    AUTH_SERVICE_URL,
    "/api/v1/documents":  PDF_SERVICE_URL,
    "/api/v1/signatures": PDF_SERVICE_URL,
    "/api/v1/projects":   PDF_SERVICE_URL,
    "/api/v1/folders":    PDF_SERVICE_URL,
    "/api/v1/notifications": AUTH_SERVICE_URL,
    "/api/v1/support":    AUTH_SERVICE_URL,
    "/api/v1/analytics":  AUTH_SERVICE_URL,
    "/api/v1/keys":       AUTH_SERVICE_URL,
    "/api/v1/ocr":        OCR_SERVICE_URL,
    "/api/v1/convert":    CONVERSION_SERVICE_URL,
}

_redis: aioredis.Redis | None = None
_http:  httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _http
    _redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
    _http  = httpx.AsyncClient(timeout=60.0)
    log.info("Gateway started")
    yield
    await _redis.aclose()
    await _http.aclose()
    log.info("Gateway stopped")


app = FastAPI(title="PDF Editor API Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Secure-by-default: an explicit allowlist (wildcard + credentials is unsafe and
    # rejected by browsers anyway). Override via ALLOWED_ORIGINS (comma-separated).
    allow_origins=[o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics at /metrics (request count, latency, in-progress, etc.)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# ── Security headers (OWASP A05: Security Misconfiguration) ────────────────────
_CSP = (
    "default-src 'self'; img-src 'self' data: https:; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Content-Security-Policy", _CSP)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return resp


# ── Rate Limiting ────────────────────────────────────────────────────────────

async def rate_limit(request: Request) -> None:
    if RATE_LIMIT_BYPASS_TOKEN and request.headers.get("x-ratelimit-bypass") == RATE_LIMIT_BYPASS_TOKEN:
        return
    ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:{ip}"
    try:
        count = await _redis.incr(key)
        if count == 1:
            await _redis.expire(key, RATE_LIMIT_WINDOW)
    except Exception:
        # Fail OPEN: if Redis (the limiter backend) is unavailable, don't take the
        # whole API down — allow the request. Availability > rate limiting here.
        log.warning("rate limiter unavailable (redis) — allowing request")
        return
    if count > RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests")


# ── Auth Token Forwarding ────────────────────────────────────────────────────

async def validate_token(request: Request) -> dict | None:
    # Prefer the Authorization header (set by the axios client), but fall back to
    # the access_token cookie so requests that can't set headers — e.g. <img> tags
    # rendering PDF pages — still authenticate.
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
    else:
        token = request.cookies.get("access_token")
    if not token:
        return None
    data = await _validate_token_str(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return data


async def _validate_token_str(token: str) -> dict | None:
    """Validate a raw JWT string via auth_service; returns user info or None."""
    if not token:
        return None
    try:
        resp = await _http.post(f"{AUTH_SERVICE_URL}/internal/validate", json={"token": token})
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data if data.get("valid") else None
    except Exception:
        return None


# ── Proxy Helper ─────────────────────────────────────────────────────────────

async def proxy(request: Request, upstream: str, extra_headers: dict | None = None) -> httpx.Response:
    url = upstream + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    body = await request.body()
    headers = dict(request.headers)
    headers.pop("host", None)
    if extra_headers:
        headers.update(extra_headers)
    resp = await _http.request(
        method=request.method,
        url=url,
        content=body,
        headers=headers,
    )
    return resp


# ── Routes ───────────────────────────────────────────────────────────────────

@app.api_route(
    "/api/v1/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def gateway_handler(
    request: Request,
    path: str,
    _rl=Depends(rate_limit),
):
    start = time.time()
    matched_upstream: str | None = None

    full_path = f"/api/v1/{path}"
    for prefix, upstream in SERVICE_MAP.items():
        if full_path.startswith(prefix):
            matched_upstream = upstream
            break

    if not matched_upstream:
        raise HTTPException(status_code=404, detail="Service not found")

    # Public routes: auth endpoints and payment-provider webhooks (Stripe/PayPal/
    # Razorpay can't send a JWT — each is authenticated by its own signature inside
    # the billing service).
    is_public = full_path.startswith("/api/v1/auth") or full_path.startswith("/api/v1/billing/webhook")

    extra_headers: dict = {}
    if not is_public:
        user_info = await validate_token(request)
        if not user_info:
            # Fall back to an enterprise API key (X-API-Key) for programmatic access.
            api_key = request.headers.get("x-api-key")
            if api_key:
                resp = await _http.post(f"{AUTH_SERVICE_URL}/internal/validate-key", json={"key": api_key})
                if resp.status_code == 200 and resp.json().get("valid"):
                    user_info = resp.json()
        if not user_info:
            raise HTTPException(status_code=401, detail="Authentication required")
        extra_headers["x-user-id"]    = user_info["user_id"]
        extra_headers["x-user-email"] = user_info.get("email", "")
        extra_headers["x-user-role"]  = user_info.get("role", "")

    try:
        resp = await proxy(request, matched_upstream, extra_headers)
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Upstream service unavailable")

    elapsed = (time.time() - start) * 1000
    log.info(f"{request.method} {full_path} -> {resp.status_code} ({elapsed:.1f}ms)")

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers={
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
        },
    )


@app.exception_handler(ClientDisconnect)
async def _client_disconnect(request: Request, exc: ClientDisconnect):
    # The caller dropped the connection mid-request (common on load-test ramp-down,
    # page navigation, cancelled uploads). Nothing to send back — return quietly with
    # 499 (client-closed-request) instead of logging a full traceback that would
    # otherwise flood production logs and hide real errors.
    log.info(f"client disconnected: {request.method} {request.url.path}")
    return Response(status_code=499)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


# ── Real-time collaboration (WebSocket + Redis pub/sub) ───────────────────────

class RoomManager:
    """Per-document collaboration rooms. Local connections + Redis pub/sub so the
    room spans all gateway replicas (horizontally scalable)."""
    def __init__(self):
        self.local: dict[str, set[WebSocket]] = {}
        self.tasks: dict[str, asyncio.Task] = {}

    async def join(self, room: str, ws: WebSocket):
        self.local.setdefault(room, set()).add(ws)
        if room not in self.tasks:
            self.tasks[room] = asyncio.create_task(self._fanout(room))

    async def leave(self, room: str, ws: WebSocket):
        conns = self.local.get(room)
        if conns:
            conns.discard(ws)
            if not conns:
                self.local.pop(room, None)
                t = self.tasks.pop(room, None)
                if t:
                    t.cancel()

    async def publish(self, room: str, message: str):
        await _redis.publish(f"collab:{room}", message)

    async def _fanout(self, room: str):
        pubsub = _redis.pubsub()
        await pubsub.subscribe(f"collab:{room}")
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                data = msg["data"]
                for ws in list(self.local.get(room, ())):
                    try:
                        await ws.send_text(data)
                    except Exception:
                        await self.leave(room, ws)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(f"collab:{room}")
            await pubsub.aclose()


rooms = RoomManager()


@app.websocket("/ws/documents/{doc_id}")
async def collab_ws(websocket: WebSocket, doc_id: str):
    # Browsers can't set Authorization on a WebSocket → token comes as a query param.
    user = await _validate_token_str(websocket.query_params.get("token", ""))
    await websocket.accept()
    if not user:
        # accept first: closing an un-accepted socket rejects the handshake (client
        # sees 1006) and the 4401 auth code would never reach the browser
        await websocket.close(code=4401)
        return
    uid = user["user_id"]
    await rooms.join(doc_id, websocket)
    await rooms.publish(doc_id, json.dumps({"type": "presence", "event": "join", "user_id": uid}))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except Exception:
                continue
            # stamp the sender; clients use this for cursors / live edits
            payload["user_id"] = uid
            await rooms.publish(doc_id, json.dumps(payload))
    except WebSocketDisconnect:
        pass
    finally:
        await rooms.leave(doc_id, websocket)
        await rooms.publish(doc_id, json.dumps({"type": "presence", "event": "leave", "user_id": uid}))
