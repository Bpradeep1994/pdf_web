from datetime import datetime, timedelta, timezone
from uuid import UUID
import secrets

import httpx
import pyotp
import qrcode
import redis.asyncio as aioredis
import io
import base64
import os

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from urllib.parse import urlencode
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, text

from shared.database import get_db
from shared.audit import record as audit
from shared.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, hash_token,
)
from models import User, RefreshToken, UserToken, UserRole, AuthProvider
from emailer import send_verification, send_password_reset
from shared.crypto import encrypt, decrypt
from schemas import (
    RegisterRequest, LoginRequest, TokenResponse, RefreshRequest,
    UserResponse, PasswordResetRequest, PasswordResetConfirm,
    ChangePasswordRequest, UpdateProfileRequest, VerifyEmailRequest, OAuthCallbackRequest,
    MFASetupResponse, MFAVerifyRequest,
    InternalValidateRequest, InternalValidateResponse,
)

router         = APIRouter()
internal_router = APIRouter()
bearer         = HTTPBearer(auto_error=False)

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS   = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS",   7))
GOOGLE_CLIENT_ID            = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET        = os.getenv("GOOGLE_CLIENT_SECRET", "")
GITHUB_CLIENT_ID            = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET        = os.getenv("GITHUB_CLIENT_SECRET", "")
MICROSOFT_CLIENT_ID         = os.getenv("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET     = os.getenv("MICROSOFT_CLIENT_SECRET", "")
OAUTH_REDIRECT_BASE         = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000/api/v1/auth")
FRONTEND_URL                = os.getenv("NEXT_PUBLIC_APP_URL", "http://localhost:3000")

# provider → (client_id, authorize_url, default_scope)
_OAUTH_PROVIDERS = {
    "google":    (GOOGLE_CLIENT_ID,    "https://accounts.google.com/o/oauth2/v2/auth", "openid email profile"),
    "github":    (GITHUB_CLIENT_ID,    "https://github.com/login/oauth/authorize",      "read:user user:email"),
    "microsoft": (MICROSOFT_CLIENT_ID, "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", "openid email profile"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_tokens(user: User) -> tuple[TokenResponse, str]:
    access = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role.value},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    raw_refresh, hashed_refresh = create_refresh_token()
    return TokenResponse(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ), hashed_refresh


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ── Auth Routes ───────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()

    token_resp, hashed_refresh = _make_tokens(user)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hashed_refresh,
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    # issue + email an email-verification token
    verify_token = secrets.token_urlsafe(32)
    db.add(UserToken(
        user_id=user.id, token=verify_token, token_type="email_verify",
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    ))
    bg.add_task(send_verification, user.email, verify_token)
    await audit(db, action="user.register", user_id=user.id, request=request)
    return token_resp


# ── Brute-force / account lockout (Redis) ─────────────────────────────────────

REDIS_URL          = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECS = int(os.getenv("LOGIN_LOCKOUT_WINDOW", "900"))  # 15 min
_redis: aioredis.Redis | None = None


def _redis_client() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def _check_lockout(email: str):
    try:
        n = int(await _redis_client().get(f"login_fail:{email.lower()}") or 0)
    except Exception:
        return  # fail-open if Redis is unavailable (don't block all logins)
    if n >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429,
                            detail="Account temporarily locked after too many failed attempts. Try again later.")


async def _record_failure(email: str):
    try:
        r = _redis_client()
        k = f"login_fail:{email.lower()}"
        cnt = await r.incr(k)
        if cnt == 1:
            await r.expire(k, LOGIN_LOCKOUT_SECS)
    except Exception:
        pass


async def _clear_failures(email: str):
    try:
        await _redis_client().delete(f"login_fail:{email.lower()}")
    except Exception:
        pass


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await _check_lockout(body.email)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        await _record_failure(body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Block suspended / banned / deactivated accounts with a clear message.
    if getattr(user, "status", "active") == "banned":
        raise HTTPException(status_code=403, detail="Your account has been banned.")
    if getattr(user, "status", "active") == "suspended":
        raise HTTPException(status_code=403, detail="Your account is suspended. Contact support.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Your account is disabled.")

    # Enforce MFA when the account has it enabled.
    if user.mfa_enabled and user.mfa_secret:
        if not body.mfa_code:
            raise HTTPException(
                status_code=401,
                detail="MFA code required",
                headers={"X-MFA-Required": "true"},
            )
        if not pyotp.TOTP(decrypt(user.mfa_secret)).verify(body.mfa_code):
            await _record_failure(body.email)
            raise HTTPException(status_code=401, detail="Invalid MFA code")

    await _clear_failures(body.email)
    await db.execute(update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc)))

    token_resp, hashed_refresh = _make_tokens(user)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hashed_refresh,
        device=body.device,
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await audit(db, action="user.login", user_id=user.id, request=request)
    return token_resp


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    hashed = hash_token(body.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hashed,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    rt = result.scalar_one_or_none()
    if not rt:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    await db.execute(
        update(RefreshToken).where(RefreshToken.id == rt.id).values(revoked_at=datetime.now(timezone.utc))
    )

    user_result = await db.execute(select(User).where(User.id == rt.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    token_resp, new_hashed = _make_tokens(user)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=new_hashed,
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    return token_resp


@router.post("/logout")
async def logout(body: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    hashed = hash_token(body.refresh_token)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hashed)
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await audit(db, action="user.logout", request=request)
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(_get_current_user)):
    return current_user


_ENUM_FALLBACK = {
    "document:read", "document:write", "document:delete", "document:share",
    "document:convert", "comment:write", "signature:request", "billing:manage",
}


@router.get("/permissions")
async def my_permissions(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    """Effective permissions from the relational RBAC tables, falling back to the
    legacy users.role enum when a user has no role rows yet."""
    perms = set((await db.execute(text(
        "SELECT DISTINCT p.name FROM user_roles ur "
        "JOIN role_permissions rp ON rp.role_id = ur.role_id "
        "JOIN permissions p ON p.id = rp.permission_id "
        "WHERE ur.user_id = CAST(:u AS uuid)"), {"u": str(current_user.id)})).scalars().all())
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if not perms:
        perms = {"*"} if role == "admin" else set(_ENUM_FALLBACK)
    return {"role": role, "permissions": sorted(perms)}


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    values = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if values:
        await db.execute(update(User).where(User.id == current_user.id).values(**values))
        await db.flush()
        result = await db.execute(select(User).where(User.id == current_user.id))
        return result.scalar_one()
    return current_user


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.hashed_password or not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.execute(update(User).where(User.id == current_user.id).values(
        hashed_password=hash_password(body.new_password)))
    # Revoke existing refresh tokens so other sessions must re-auth.
    await db.execute(update(RefreshToken).where(
        RefreshToken.user_id == current_user.id, RefreshToken.revoked_at.is_(None)
    ).values(revoked_at=datetime.now(timezone.utc)))
    await audit(db, action="user.password_changed", user_id=current_user.id, request=request)
    return {"message": "Password changed"}


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(select(UserToken).where(
        UserToken.token == body.token, UserToken.token_type == "email_verify",
        UserToken.used_at.is_(None)))).scalar_one_or_none()
    if not row or row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    await db.execute(update(User).where(User.id == row.user_id).values(is_verified=True))
    await db.execute(update(UserToken).where(UserToken.id == row.id).values(used_at=datetime.now(timezone.utc)))
    return {"message": "Email verified"}


@router.post("/resend-verification")
async def resend_verification(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.is_verified:
        return {"message": "Already verified"}
    token = secrets.token_urlsafe(32)
    db.add(UserToken(user_id=current_user.id, token=token, token_type="email_verify",
                     expires_at=datetime.now(timezone.utc) + timedelta(days=2)))
    resp = {"message": "Verification email sent"}
    if os.getenv("ENVIRONMENT", "development").lower() not in ("production", "prod", "staging"):
        resp["token"] = token   # dev convenience so the flow is testable without email
    return resp


@router.post("/password-reset")
async def request_password_reset(body: PasswordResetRequest, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(32)
        db.add(UserToken(
            user_id=user.id,
            token=token,
            token_type="password_reset",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        bg.add_task(send_password_reset, user.email, token)
    return {"message": "If that email exists, a reset link has been sent"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(body: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserToken).where(
            UserToken.token == body.token,
            UserToken.token_type == "password_reset",
            UserToken.used_at.is_(None),
            UserToken.expires_at > datetime.now(timezone.utc),
        )
    )
    token_row = result.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    await db.execute(
        update(User).where(User.id == token_row.user_id).values(hashed_password=hash_password(body.password))
    )
    await db.execute(
        update(UserToken).where(UserToken.id == token_row.id).values(used_at=datetime.now(timezone.utc))
    )
    return {"message": "Password updated"}


# ── OAuth ─────────────────────────────────────────────────────────────────────

@router.get("/oauth/providers")
async def oauth_providers():
    """Which social-login providers are actually configured. The frontend uses this
    to only show buttons that work (so users never hit an 'not configured' error)."""
    return {"providers": [name for name, (cid, _u, _s) in _OAUTH_PROVIDERS.items() if cid]}


@router.get("/oauth/{provider}")
async def oauth_start(provider: str):
    """Redirect the user to the provider's consent screen."""
    cfg = _OAUTH_PROVIDERS.get(provider)
    if not cfg:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    client_id, authorize_url, scope = cfg
    if not client_id:
        raise HTTPException(status_code=503, detail=f"{provider} OAuth is not configured")
    params = {
        "client_id": client_id,
        "redirect_uri": f"{OAUTH_REDIRECT_BASE}/oauth/{provider}/callback",
        "response_type": "code",
        "scope": scope,
    }
    return RedirectResponse(f"{authorize_url}?{urlencode(params)}")


async def _resolve_oauth(provider: str, code: str):
    if provider == "google":
        return await _google_user_info(code), AuthProvider.google
    if provider == "github":
        return await _github_user_info(code), AuthProvider.github
    if provider == "microsoft":
        return await _microsoft_user_info(code), AuthProvider.microsoft
    raise HTTPException(status_code=400, detail="Unsupported provider")


async def _upsert_oauth_user(user_info: dict, provider: AuthProvider, request: Request, db: AsyncSession):
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Provider did not return an email")
    full_name  = user_info.get("name", "")
    avatar_url = user_info.get("avatar_url") or user_info.get("picture")

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if not user:
        user = User(email=email, full_name=full_name, avatar_url=avatar_url,
                    auth_provider=provider, provider_id=str(user_info.get("id", "")), is_verified=True)
        db.add(user)
        await db.flush()
    else:
        await db.execute(update(User).where(User.id == user.id).values(
            avatar_url=avatar_url, last_login_at=datetime.now(timezone.utc)))

    token_resp, hashed_refresh = _make_tokens(user)
    db.add(RefreshToken(user_id=user.id, token_hash=hashed_refresh,
                        ip_address=request.client.host if request.client else None,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)))
    await audit(db, action="user.oauth_login", user_id=user.id, request=request,
                metadata={"provider": provider.value})
    return token_resp


@router.get("/oauth/{provider}/callback")
async def oauth_redirect_callback(provider: str, code: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Provider redirects here with ?code=…; we exchange it and hand tokens to the SPA."""
    user_info, prov = await _resolve_oauth(provider, code)
    tokens = await _upsert_oauth_user(user_info, prov, request, db)
    # Pass tokens to the frontend callback page (which stores them and redirects).
    frag = urlencode({"access_token": tokens.access_token, "refresh_token": tokens.refresh_token})
    return RedirectResponse(f"{FRONTEND_URL}/oauth/callback#{frag}")


@router.post("/oauth/callback", response_model=TokenResponse)
async def oauth_callback(body: OAuthCallbackRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """SPA-driven flow: frontend sends {provider, code}, we return tokens as JSON."""
    user_info, provider = await _resolve_oauth(body.provider, body.code)
    return await _upsert_oauth_user(user_info, provider, request, db)


async def _google_user_info(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
                "grant_type": "authorization_code",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        user_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        return user_resp.json()


async def _github_user_info(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "code": code,
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
            },
            headers={"Accept": "application/json"},
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()

        if not user_data.get("email"):
            emails_resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            primary = next(e for e in emails_resp.json() if e["primary"])
            user_data["email"] = primary["email"]

        return user_data


async def _microsoft_user_info(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "code": code,
                "client_id": MICROSOFT_CLIENT_ID,
                "client_secret": MICROSOFT_CLIENT_SECRET,
                "redirect_uri": f"{OAUTH_REDIRECT_BASE}/oauth/microsoft/callback",
                "grant_type": "authorization_code",
                "scope": "openid email profile",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        user_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_resp.raise_for_status()
        u = user_resp.json()
        return {
            "id": u.get("id"),
            "email": u.get("mail") or u.get("userPrincipalName"),
            "name": u.get("displayName", ""),
        }


# ── MFA ───────────────────────────────────────────────────────────────────────

@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    secret = pyotp.random_base32()
    totp   = pyotp.TOTP(secret)
    qr_url = totp.provisioning_uri(name=current_user.email, issuer_name="PDFEditor")

    await db.execute(update(User).where(User.id == current_user.id).values(mfa_secret=encrypt(secret)))
    return MFASetupResponse(secret=secret, qr_url=qr_url)


@router.post("/mfa/verify")
async def verify_mfa(body: MFAVerifyRequest, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA not set up")

    totp = pyotp.TOTP(decrypt(current_user.mfa_secret))
    if not totp.verify(body.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")

    await db.execute(update(User).where(User.id == current_user.id).values(mfa_enabled=True))
    return {"message": "MFA enabled"}


# ── Internal (service-to-service) ─────────────────────────────────────────────

@internal_router.post("/validate", response_model=InternalValidateResponse)
async def internal_validate(body: InternalValidateRequest):
    try:
        payload = decode_token(body.token)
        return InternalValidateResponse(
            user_id=payload["sub"],
            email=payload["email"],
            role=payload["role"],
            valid=True,
        )
    except Exception:
        return InternalValidateResponse(user_id="", email="", role="", valid=False)
