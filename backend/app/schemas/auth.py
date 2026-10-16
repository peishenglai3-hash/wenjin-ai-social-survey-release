"""Pydantic schemas for authentication requests and responses.

Supports: email+password, phone+SMS, WeChat OAuth, account binding.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ═══════════════════════════════════════════════════════════════
# Email auth (existing)
# ═══════════════════════════════════════════════════════════════

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    captcha_token: str = Field(..., description="CAPTCHA token from GET /auth/captcha")
    captcha_answer: str = Field(..., min_length=4, max_length=6, description="User's CAPTCHA answer")


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ═══════════════════════════════════════════════════════════════
# Phone + SMS auth (NEW)
# ═══════════════════════════════════════════════════════════════

class SendSmsRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+?1[3-9]\d{9}$", description="Chinese mobile number")
    captcha_token: str
    captcha_answer: str = Field(..., min_length=4, max_length=6)


class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+?1[3-9]\d{9}$")
    sms_code: str = Field(..., min_length=6, max_length=6)


class PhoneRegisterRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+?1[3-9]\d{9}$")
    sms_code: str = Field(..., min_length=6, max_length=6)
    display_name: str = Field(default="", max_length=100)
    captcha_token: str
    captcha_answer: str = Field(..., min_length=4, max_length=6)


# ═══════════════════════════════════════════════════════════════
# WeChat OAuth (NEW)
# ═══════════════════════════════════════════════════════════════

class WechatLoginRequest(BaseModel):
    code: str = Field(..., description="WeChat OAuth authorization code")
    state: str = Field(..., description="CSRF state token")


# ═══════════════════════════════════════════════════════════════
# Account binding (NEW)
# ═══════════════════════════════════════════════════════════════

class BindPhoneRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+?1[3-9]\d{9}$")
    sms_code: str = Field(..., min_length=6, max_length=6)


# ═══════════════════════════════════════════════════════════════
# Token responses (existing)
# ═══════════════════════════════════════════════════════════════

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 1800


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


# ═══════════════════════════════════════════════════════════════
# User info (extended)
# ═══════════════════════════════════════════════════════════════

class AuthMethodInfo(BaseModel):
    auth_type: str
    identifier: str  # Masked for display (e.g. "+86138****0000")
    verified: bool
    is_primary: bool


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    phone: Optional[str] = None
    wechat_bound: bool = False
    real_name_verified: bool = False
    auth_methods: list[AuthMethodInfo] = []

    model_config = {"from_attributes": True}


class CaptchaResponse(BaseModel):
    captcha_token: str
    svg: str  # Raw SVG markup (inline)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ═══════════════════════════════════════════════════════════════
# PIPL compliance (NEW — data export / account deletion)
# ═══════════════════════════════════════════════════════════════

class DataExportResponse(BaseModel):
    """Response when user requests their data under PIPL Article 45."""
    user: UserResponse
    surveys_count: int
    memories_count: int
    export_generated_at: datetime


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., description="Current password for confirmation")


# ═══════════════════════════════════════════════════════════════
# ORCID OAuth (NEW)
# ═══════════════════════════════════════════════════════════════

class OrcidAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str  # CSRF state token — store in sessionStorage, pass to callback


class OrcidExchangeRequest(BaseModel):
    auth_code: str = Field(..., description="Short-lived auth code from /auth/orcid/callback redirect")
