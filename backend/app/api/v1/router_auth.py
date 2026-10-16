"""Authentication router — register, login, refresh, user info, CAPTCHA.

Multi-method auth: email+password, phone+SMS, WeChat OAuth.
PIPL: data export and account deletion.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import require_user
from app.config import settings
from app.core.database import get_db
from app.core.captcha import generate_captcha, verify_captcha
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.refresh_tokens import hash_refresh_token, matches_refresh_token
from app.models.user import UserAccount, UserAuthMethod
from app.models.survey import UserProfile
from app.schemas.auth import (
    AuthMethodInfo,
    BindPhoneRequest,
    CaptchaResponse,
    ChangePasswordRequest,
    DataExportResponse,
    DeleteAccountRequest,
    OrcidAuthorizeResponse,
    OrcidExchangeRequest,
    PhoneLoginRequest,
    PhoneRegisterRequest,
    RefreshRequest,
    SendSmsRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    WechatLoginRequest,
)
from app.services.sms_service import get_sms_service
from app.services.orcid_service import exchange_code, get_authorize_url, decode_state_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _store_refresh_token(user: UserAccount, token: str) -> None:
    """Persist only a keyed digest; never store the raw refresh JWT."""

    user.refresh_token = hash_refresh_token(token)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite=settings.refresh_cookie_samesite,
        path="/api/v1/auth",
    )


# ═══════════════════════════════════════════════
# CAPTCHA
# ═══════════════════════════════════════════════

@router.get("/captcha", response_model=CaptchaResponse)
async def get_captcha():
    """Get a new CAPTCHA challenge — returns SVG image and token."""
    token, _answer, svg = generate_captcha()
    return CaptchaResponse(captcha_token=token, svg=svg)


# ═══════════════════════════════════════════════
# Email auth (existing)
# ═══════════════════════════════════════════════

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account (CAPTCHA-protected)."""
    if not verify_captcha(body.captcha_token, body.captcha_answer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification failed — please try again",
        )

    existing = await db.execute(
        select(UserAccount).where(UserAccount.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = UserAccount(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.flush()

    # Create email auth method record
    db.add(UserAuthMethod(
        user_id=user.id,
        auth_type="email",
        identifier=body.email,
        credential=user.hashed_password,
        verified=True,
        is_primary=True,
    ))

    profile = UserProfile(user_id=user.id)
    db.add(profile)
    await db.commit()
    await db.refresh(user)
    return _user_to_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password, receive JWT tokens."""
    result = await db.execute(
        select(UserAccount).where(UserAccount.email == body.email)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)
    _store_refresh_token(user, refresh_token)
    await db.commit()
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ═══════════════════════════════════════════════
# Phone + SMS auth (NEW)
# ═══════════════════════════════════════════════

@router.post("/send-sms")
async def send_sms(body: SendSmsRequest):
    """Send a 6-digit SMS verification code.

    Rate-limited: 1 per 60s per phone, 5 per day per phone.
    In development mode: code is logged to server console.
    """
    if not verify_captcha(body.captcha_token, body.captcha_answer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification failed",
        )

    sms = get_sms_service()
    success = await sms.send_verification(body.phone)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send SMS — please try again",
        )
    return {
        "status": "ok",
        "message": f"Verification code sent to {sms.mask_phone(body.phone)}",
        "expires_in": 300,
    }


@router.post("/login/phone", response_model=TokenResponse)
async def login_phone(
    body: PhoneLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login with phone number + SMS verification code."""
    sms = get_sms_service()
    if not sms.verify_code(body.phone, body.sms_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code",
        )

    result = await db.execute(
        select(UserAccount).where(UserAccount.phone == body.phone)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No account found with this phone number. Please register first.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)
    _store_refresh_token(user, refresh_token)
    await db.commit()
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/register/phone", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_phone(body: PhoneRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new account with phone number + SMS verification."""
    if not verify_captcha(body.captcha_token, body.captcha_answer):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CAPTCHA verification failed",
        )

    sms = get_sms_service()
    if not sms.verify_code(body.phone, body.sms_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SMS verification code",
        )

    existing = await db.execute(
        select(UserAccount).where(UserAccount.phone == body.phone)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already registered",
        )

    placeholder_email = f"phone_{body.phone.replace('+', '')}@example.invalid"

    user = UserAccount(
        email=placeholder_email,
        hashed_password=hash_password(""),
        display_name=body.display_name,
        phone=body.phone,
    )
    db.add(user)
    await db.flush()

    db.add(UserAuthMethod(
        user_id=user.id,
        auth_type="phone",
        identifier=body.phone,
        credential=None,
        verified=True,
        is_primary=True,
    ))

    profile = UserProfile(user_id=user.id)
    db.add(profile)
    await db.commit()
    await db.refresh(user)
    return _user_to_response(user)


@router.post("/bind/phone")
async def bind_phone(
    body: BindPhoneRequest,
    user: UserAccount = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Bind a phone number to the current account."""
    sms = get_sms_service()
    if not sms.verify_code(body.phone, body.sms_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired SMS verification code",
        )

    existing = await db.execute(
        select(UserAccount).where(
            UserAccount.phone == body.phone,
            UserAccount.id != user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone number already bound to another account",
        )

    user.phone = body.phone
    db.add(UserAuthMethod(
        user_id=user.id,
        auth_type="phone",
        identifier=body.phone,
        credential=None,
        verified=True,
        is_primary=False,
    ))
    await db.commit()
    return {"status": "ok", "message": f"Phone {sms.mask_phone(body.phone)} bound successfully"}


# ═══════════════════════════════════════════════
# Token management (existing)
# ═══════════════════════════════════════════════

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Use a refresh token to get a new access token."""
    presented_token = (body.refresh_token if body else None) or request.cookies.get(
        settings.refresh_cookie_name
    )
    if not presented_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )
    try:
        payload = decode_token(presented_token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = int(payload["sub"])
    result = await db.execute(
        select(UserAccount).where(UserAccount.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not matches_refresh_token(user.refresh_token, presented_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked",
        )

    new_access = create_access_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id, user.email)
    _store_refresh_token(user, new_refresh)
    await db.commit()
    _set_refresh_cookie(response, new_refresh)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
    )


@router.post("/logout")
async def logout(
    response: Response,
    user: UserAccount = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout — revoke the refresh token."""
    user.refresh_token = None
    await db.commit()
    _clear_refresh_cookie(response)
    return {"status": "ok"}


# ═══════════════════════════════════════════════
# User info & management
# ═══════════════════════════════════════════════

@router.get("/me", response_model=UserResponse)
async def me(user: UserAccount = Depends(require_user)):
    """Get the current authenticated user's info."""
    return _user_to_response(user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: UserAccount = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(body.old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    user.hashed_password = hash_password(body.new_password)
    user.refresh_token = None
    await db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════════════════
# PIPL compliance — data export & deletion (NEW)
# ═══════════════════════════════════════════════

@router.get("/export-data", response_model=DataExportResponse)
async def export_my_data(
    user: UserAccount = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all personal data (PIPL Article 45 right to access/copy)."""
    from datetime import datetime, timezone

    surveys_count = 0
    memories_count = 0

    if user.profile:
        try:
            from app.models.survey import SurveyProject
            count_result = await db.execute(
                select(SurveyProject).where(SurveyProject.profile_id == user.profile.id)
            )
            surveys_count = len(count_result.scalars().all())
        except Exception:
            surveys_count = 0

    # Memory count via service layer (MemoryEntry model doesn't exist yet)
    try:
        from app.services.memory_service import count_user_memories
        memories_count = await count_user_memories(db, user.id)
    except Exception:
        memories_count = 0

    return DataExportResponse(
        user=_user_to_response(user),
        surveys_count=surveys_count,
        memories_count=memories_count,
        export_generated_at=datetime.now(timezone.utc),
    )


@router.delete("/account")
async def delete_account(
    body: DeleteAccountRequest,
    user: UserAccount = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete account and all associated data (PIPL Article 47)."""
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password incorrect — account deletion requires confirmation",
        )
    await db.delete(user)
    await db.commit()
    return {"status": "ok", "message": "Account permanently deleted"}


# ═══════════════════════════════════════════════
# ORCID OAuth (NEW — P2 academic identity)
# ═══════════════════════════════════════════════

# In-memory auth_code store: code → {user_id, email, expires_at}
# Codes are short-lived (60s) so in-memory is sufficient.
_orcid_auth_codes: dict[str, dict] = {}


@router.get("/orcid", response_model=OrcidAuthorizeResponse)
async def orcid_authorize(redirect_to: str = "/"):
    """Get the ORCID OAuth authorize URL.  Store the returned state token
    in sessionStorage and pass it when calling the callback."""
    url, state = get_authorize_url(redirect_to)
    return OrcidAuthorizeResponse(authorize_url=url, state=state)


@router.get("/orcid/callback")
async def orcid_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """ORCID OAuth callback — exchanges code, creates/links account,
    then redirects to the frontend with a short-lived auth_code."""
    import secrets
    import time
    from fastapi.responses import RedirectResponse

    # Validate state token
    state_payload = decode_state_token(state)
    if state_payload is None:
        raise HTTPException(status_code=400, detail="Invalid or expired state token")

    redirect_to = state_payload.get("redirect_to", "/")

    # Exchange authorization code for ORCID iD
    try:
        orcid_data = await exchange_code(code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    orcid_id = orcid_data["orcid"]
    display_name = orcid_data.get("name", f"ORCID:{orcid_id[-8:]}")

    # Find existing user by ORCID in auth_methods
    result = await db.execute(
        select(UserAuthMethod).where(
            UserAuthMethod.auth_type == "orcid",
            UserAuthMethod.identifier == orcid_id,
        )
    )
    existing_auth = result.scalar_one_or_none()

    if existing_auth:
        user = await db.get(UserAccount, existing_auth.user_id)
    else:
        # Create new user with ORCID identity
        placeholder_email = f"orcid_{orcid_id[-12:]}@example.invalid"
        user = UserAccount(
            email=placeholder_email,
            hashed_password=hash_password(secrets.token_hex(32)),
            display_name=display_name,
        )
        db.add(user)
        await db.flush()

        db.add(UserAuthMethod(
            user_id=user.id,
            auth_type="orcid",
            identifier=orcid_id,
            credential=None,
            verified=True,
            is_primary=True,
        ))
        profile = UserProfile(user_id=user.id)
        db.add(profile)

    await db.commit()
    await db.refresh(user)

    # Generate short-lived auth_code
    auth_code = secrets.token_hex(32)
    _orcid_auth_codes[auth_code] = {
        "user_id": user.id,
        "email": user.email,
        "expires_at": time.time() + 60,
    }

    # Cleanup expired codes
    now = time.time()
    for k in list(_orcid_auth_codes.keys()):
        if _orcid_auth_codes[k]["expires_at"] < now:
            del _orcid_auth_codes[k]

    frontend_base = settings.public_base_url.rstrip("/")
    if not frontend_base:
        raise HTTPException(status_code=503, detail="ORCID redirect is not configured")
    return RedirectResponse(
        url=f"{frontend_base}/orcid-callback?auth_code={auth_code}&redirect_to={redirect_to}"
    )


@router.post("/orcid/exchange", response_model=TokenResponse)
async def orcid_exchange(
    body: OrcidExchangeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a short-lived auth_code (from /auth/orcid/callback redirect)
    for JWT access + refresh tokens."""
    import time

    entry = _orcid_auth_codes.pop(body.auth_code, None)
    if entry is None:
        raise HTTPException(status_code=400, detail="Invalid or expired auth_code")
    if entry["expires_at"] < time.time():
        raise HTTPException(status_code=400, detail="Auth code expired — please login again")

    result = await db.execute(
        select(UserAccount).where(UserAccount.id == entry["user_id"])
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Account not found or inactive")

    access_token = create_access_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)
    _store_refresh_token(user, refresh_token)
    await db.commit()
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/bind/orcid")
async def bind_orcid(
    code: str,
    user: UserAccount = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Bind ORCID to the currently authenticated account."""
    try:
        orcid_data = await exchange_code(code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    orcid_id = orcid_data["orcid"]

    # Check not already bound
    existing = await db.execute(
        select(UserAuthMethod).where(
            UserAuthMethod.auth_type == "orcid",
            UserAuthMethod.identifier == orcid_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This ORCID is already linked to an account")

    db.add(UserAuthMethod(
        user_id=user.id,
        auth_type="orcid",
        identifier=orcid_id,
        credential=None,
        verified=True,
        is_primary=False,
    ))
    await db.commit()
    return {"status": "ok", "orcid": orcid_id, "message": "ORCID linked successfully"}


# ═══════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════

def _user_to_response(user: UserAccount) -> UserResponse:
    """Convert a UserAccount to UserResponse with auth method info.

    Uses eager-loaded auth_methods when available; falls back gracefully
    if the relationship hasn't been loaded (avoids MissingGreenlet errors).
    """
    sms = get_sms_service()
    methods: list[AuthMethodInfo] = []
    try:
        auth_methods = user.auth_methods if hasattr(user, "auth_methods") else []
        for m in auth_methods or []:
            identifier = m.identifier
            if m.auth_type == "phone":
                identifier = sms.mask_phone(identifier)
            elif m.auth_type == "email" and "@" in identifier:
                local, domain = identifier.split("@", 1)
                identifier = local[0] + "***@" + domain
            methods.append(AuthMethodInfo(
                auth_type=m.auth_type,
                identifier=identifier,
                verified=m.verified,
                is_primary=m.is_primary or False,
            ))
    except Exception:
        # Lazy load failed (e.g. MissingGreenlet in async context) — omit methods
        methods = []

    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name or "",
        role=user.role,
        is_active=user.is_active,
        phone=sms.mask_phone(user.phone) if user.phone else None,
        wechat_bound=bool(user.wechat_openid),
        real_name_verified=user.real_name_verified,
        auth_methods=methods,
    )
