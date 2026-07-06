"""Dependency helpers for retrieving the authenticated user."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.user_model import UserModel
from src.utils.auth.jwt import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> UserModel:
    """Validate the JWT token and return the associated user.

    Raises:
        HTTPException: 401 when the token is invalid, expired, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload: dict = decode_access_token(token)
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            raise credentials_exception
        user_id = int(user_id_raw)
    except Exception:
        raise credentials_exception

    user: UserModel | None = db.execute(select(UserModel).where(UserModel.id == user_id)).scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user
