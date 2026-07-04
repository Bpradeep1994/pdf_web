from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from uuid import UUID
from models import UserRole, AuthProvider


class RegisterRequest(BaseModel):
    email:     EmailStr
    password:  str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str
    device:   str | None = None
    mfa_code: str | None = None


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id:            UUID
    email:         str
    full_name:     str | None
    avatar_url:    str | None
    role:          UserRole
    admin_level:   str = "user"
    status:        str = "active"
    auth_provider: AuthProvider
    is_verified:   bool
    mfa_enabled:   bool
    created_at:    datetime

    model_config = {"from_attributes": True}


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token:    str
    password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str = Field(min_length=8)


class UpdateProfileRequest(BaseModel):
    full_name:  str | None = Field(default=None, max_length=255)
    avatar_url: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str


class OAuthCallbackRequest(BaseModel):
    code:     str
    state:    str | None = None
    provider: str


class MFASetupResponse(BaseModel):
    secret:  str
    qr_url:  str


class MFAVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class InternalValidateRequest(BaseModel):
    token: str


class InternalValidateResponse(BaseModel):
    user_id: str
    email:   str
    role:    str
    valid:   bool
