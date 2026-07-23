"""JWT issuing and verification.

Short-lived access tokens travel in the Authorization header; refresh tokens
live in an httpOnly cookie so page scripts cannot read them.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt

from app.config import settings


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    """Raised when a token is absent, malformed, expired or of the wrong type."""


def _encode(subject: str, token_type: TokenType, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _encode(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=settings.access_token_ttl_minutes),
    )


def create_refresh_token(user_id: str) -> str:
    return _encode(
        user_id,
        TokenType.REFRESH,
        timedelta(days=settings.refresh_token_ttl_days),
    )


def decode_token(token: str, expected: TokenType) -> str:
    """Return the subject (user id) or raise `TokenError`."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise TokenError("invalid token") from exc

    if payload.get("type") != expected.value:
        raise TokenError("wrong token type")
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise TokenError("missing subject")
    return subject
