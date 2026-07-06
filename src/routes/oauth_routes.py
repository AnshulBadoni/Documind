"""OAuth routes for Google and GitHub social login."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.oauth2 import get_current_user
from src.controllers.oauth_controller import OAuthController
from src.database import get_db
from src.models.user_model import UserModel
from src.schemas.oauth_schema import OAuthCallbackRequest

router = APIRouter(prefix="/auth", tags=["OAuth"])


# ---------------------------------------------------------------------------
# Provider redirect endpoints
# ---------------------------------------------------------------------------

@router.get("/google/login")
def google_login(
    state: str = Query(..., description="CSRF state parameter"),
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict:
    """Initiate Google OAuth flow and return the authorization redirect URL.

    The client should redirect the user's browser to the returned ``auth_url``.
    """
    controller = OAuthController(db)
    return controller.get_redirect_url(provider="google", state=state)


@router.get("/github/login")
def github_login(
    state: str = Query(..., description="CSRF state parameter"),
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict:
    """Initiate GitHub OAuth flow and return the authorization redirect URL.

    The client should redirect the user's browser to the returned ``auth_url``.
    """
    controller = OAuthController(db)
    return controller.get_redirect_url(provider="github", state=state)


# ---------------------------------------------------------------------------
# Callback endpoints (called by the provider after user authorizes)
# ---------------------------------------------------------------------------

@router.get("/google/callback")
async def google_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str | None = Query(default=None, description="CSRF state parameter"),
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict:
    """Handle Google OAuth callback and exchange code for a JWT token."""
    payload = OAuthCallbackRequest(code=code, state=state)
    controller = OAuthController(db)
    return await controller.callback(provider="google", payload=payload)


@router.get("/github/callback")
async def github_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str | None = Query(default=None, description="CSRF state parameter"),
    db: Annotated[Session, Depends(get_db)] = None,
) -> dict:
    """Handle GitHub OAuth callback and exchange code for a JWT token."""
    payload = OAuthCallbackRequest(code=code, state=state)
    controller = OAuthController(db)
    return await controller.callback(provider="github", payload=payload)


# ---------------------------------------------------------------------------
# Account linking endpoints (require authentication)
# ---------------------------------------------------------------------------

@router.post("/link/{provider}")
def link_account(
    provider: str,
    payload: OAuthCallbackRequest,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """Link an OAuth provider account to the current authenticated user."""
    controller = OAuthController(db)
    return controller.link_account(provider=provider, payload=payload, user=current_user)


@router.delete("/unlink/{provider}")
def unlink_account(
    provider: str,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """Unlink an OAuth provider account from the current authenticated user."""
    controller = OAuthController(db)
    return controller.unlink_account(provider=provider, user=current_user, db=db)
