"""Registration, login, refresh and profile endpoints."""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pymongo.errors import DuplicateKeyError

from app.auth.crypto import SecretStorageUnavailable, encrypt_secret
from app.auth.deps import CurrentUser
from app.auth.password import hash_password, verify_password
from app.auth.tokens import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.config import settings
from app.db.models import User
from app.schemas.auth import (
    LoginRequest,
    PreferencesUpdate,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

#: Verified against when the email is unknown, so a miss costs the same time as
#: a hit and cannot be used to enumerate accounts.
_DUMMY_HASH = hash_password("timing-equalisation-placeholder")

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
)


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        preferences=user.preferences,
        has_github_token=bool(user.github_token_encrypted),
    )


def _issue(response: Response, user_id: str) -> TokenResponse:
    """Set the refresh cookie and return a fresh access token."""
    response.set_cookie(
        REFRESH_COOKIE,
        create_refresh_token(user_id),
        httponly=True,
        samesite="lax",
        # Dev runs over plain http; enable when served behind TLS.
        secure=False,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
    )
    return TokenResponse(
        access_token=create_access_token(user_id),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response) -> TokenResponse:
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name or body.email.split("@")[0],
    )
    try:
        await user.insert()
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc

    return _issue(response, str(user.id))


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> TokenResponse:
    user = await User.find_one(User.email == body.email.lower())
    valid = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not valid:
        raise _INVALID_CREDENTIALS
    return _issue(response, str(user.id))


@router.post("/refresh")
async def refresh(
    response: Response,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    """Exchange the httpOnly refresh cookie for a new access token."""
    if not refresh_token:
        raise _INVALID_CREDENTIALS
    try:
        user_id = decode_token(refresh_token, TokenType.REFRESH)
    except TokenError as exc:
        raise _INVALID_CREDENTIALS from exc

    if await User.get(PydanticObjectId(user_id)) is None:
        raise _INVALID_CREDENTIALS
    return _issue(response, user_id)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    return {"detail": "logged out"}


@router.get("/me")
async def me(user: CurrentUser) -> UserResponse:
    return _to_response(user)


@router.patch("/me")
async def update_me(user: CurrentUser, body: PreferencesUpdate) -> UserResponse:
    if body.llm_model is not None:
        user.preferences.llm_model = body.llm_model or None
    if body.min_severity is not None:
        user.preferences.min_severity = body.min_severity
    if body.github_token is not None:
        if body.github_token == "":
            user.github_token_encrypted = None
        else:
            try:
                user.github_token_encrypted = encrypt_secret(body.github_token)
            except SecretStorageUnavailable as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Server has no FERNET_KEY configured; "
                        "refusing to store the token unencrypted"
                    ),
                ) from exc
    await user.save()
    return _to_response(user)
