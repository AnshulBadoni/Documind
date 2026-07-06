"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.controllers.auth_controller import AuthController
from src.database import get_db
from src.schemas.auth_schema import LoginRequest
from src.schemas.user_schema import UserCreate
from src.auth.oauth2 import get_current_user
from src.models.user_model import UserModel

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=201)
def register(
    payload: UserCreate,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Register a new user account.

    Args:
        payload: Validated user creation data.
        db: Injected database session.

    Returns:
        Formatted response dictionary.
    """
    controller = AuthController(db)
    return controller.register_user(payload)


@router.post("/login")
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Authenticate user and return JWT access token.

    Args:
        payload: Validated login credentials.
        db: Injected database session.

    Returns:
        Formatted response dictionary with access token.
    """
    controller = AuthController(db)
    return controller.login(payload)


@router.put("/me", status_code=200)
def update_profile(
    payload: dict,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Update current user's profile information (username)."""
    from src.services.DTO import ResponseDto
    username = payload.get("username")
    if not username:
        return ResponseDto.fail(status=400, message="Username is required")
    current_user.username = username.strip()
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return ResponseDto.ok(
        status=200,
        message="Profile updated successfully",
        data={"id": current_user.id, "email": current_user.email, "username": current_user.username},
    )
