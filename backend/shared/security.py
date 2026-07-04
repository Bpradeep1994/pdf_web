from datetime import datetime, timedelta, timezone
from typing import Any
import os
import hashlib
import logging
import secrets

import bcrypt as _bcrypt
from jose import jwt, JWTError

log = logging.getLogger("security")

# Known placeholder secrets that must never be used in production.
_WEAK_SECRETS = {
    "",
    "dev-secret-change-in-production",
    "supersecretkey",
    "change-me-to-a-random-64-char-string",
}

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SECRET_KEY  = os.getenv("SECRET_KEY", "")

if SECRET_KEY in _WEAK_SECRETS or len(SECRET_KEY) < 32:
    if ENVIRONMENT in ("production", "prod", "staging"):
        raise RuntimeError(
            "SECRET_KEY is missing, too short, or a known placeholder. "
            "Set a strong (>=32 char) random SECRET_KEY before deploying."
        )
    log.warning(
        "SECRET_KEY is weak/placeholder — acceptable for local dev only. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
    )
    if not SECRET_KEY:
        SECRET_KEY = "dev-secret-change-in-production"

ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS    = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload.update({"exp": expire, "type": "access"})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token() -> tuple[str, str]:
    """Returns (raw_token, hashed_token)."""
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
