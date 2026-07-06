"""JWT token generation and validation."""

import datetime
from typing import Any

import jwt
from jwt import PyJWTError

from src.config import get_settings


def create_access_token(data: dict[str, Any], expires_delta: datetime.timedelta | None = None) -> str:
    """Create a JWT access token.

    Args:
        data: Claims to encode in the token payload.
        expires_delta: Optional custom expiry duration.

    Returns:
        Encoded JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()

    expire = datetime.datetime.now(datetime.timezone.utc) + (
        expires_delta
        or datetime.timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Args:
        token: Raw JWT string.

    Returns:
        Decoded token payload as a dictionary.

    Raises:
        PyJWTError: When the token is invalid or has expired.
    """
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except PyJWTError as exc:
        raise exc
