from sqlalchemy import Column, String, Boolean, DateTime, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.sql import func
import uuid
from enum import Enum

from shared.database import Base


class UserRole(str, Enum):
    free       = "free"
    pro        = "pro"
    business   = "business"
    enterprise = "enterprise"
    admin      = "admin"


class AuthProvider(str, Enum):
    email     = "email"
    google    = "google"
    github    = "github"
    microsoft = "microsoft"


class User(Base):
    __tablename__ = "users"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email           = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255))
    full_name       = Column(String(255))
    avatar_url      = Column(Text)
    role            = Column(SAEnum(UserRole, name="user_role"), nullable=False, default=UserRole.free)
    auth_provider   = Column(SAEnum(AuthProvider, name="auth_provider"), nullable=False, default=AuthProvider.email)
    provider_id     = Column(String(255))
    is_verified     = Column(Boolean, nullable=False, default=False)
    is_active       = Column(Boolean, nullable=False, default=True)
    admin_level     = Column(String(20), nullable=False, default="user")    # user|moderator|admin|superadmin
    status          = Column(String(20), nullable=False, default="active")  # active|suspended|banned
    mfa_enabled     = Column(Boolean, nullable=False, default=False)
    mfa_secret      = Column(Text)   # Fernet-encrypted ('enc:' + ciphertext) — far longer than 64 chars
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login_at   = Column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), nullable=False, index=True)
    token_hash  = Column(String(255), unique=True, nullable=False)
    device      = Column(String(255))
    ip_address  = Column(INET)
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    revoked_at  = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class UserToken(Base):
    __tablename__ = "user_tokens"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    token      = Column(String(255), unique=True, nullable=False, index=True)
    token_type = Column(String(50), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at    = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
