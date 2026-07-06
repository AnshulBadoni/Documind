"""Google OAuth2 client implementation."""

import httpx
from typing import Any

from src.config import get_settings
from src.utils.oauth.config import OAuthProvider, OAuthUserInfo


GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL: str = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_AUTH_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"


def _build_authorization_url(state: str) -> str:
    """Build the Google OAuth authorization URL.

    Args:
        state: CSRF protection token.

    Returns:
        Fully-formed Google OAuth authorization URL.
    """
    settings = get_settings()
    params: dict[str, str] = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    query: str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GOOGLE_AUTH_URL}?{query}"


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange an authorization code for access and refresh tokens.

    Args:
        code: Authorization code received from Google.

    Returns:
        Dictionary containing token response from Google.

    Raises:
        httpx.HTTPStatusError: When Google returns a non-2xx response.
    """
    settings = get_settings()
    payload: dict[str, str] = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=payload)
        response.raise_for_status()
        return response.json()


async def get_user_info(access_token: str) -> dict[str, Any]:
    """Fetch user profile information from Google.

    Args:
        access_token: Google OAuth access token.

    Returns:
        Dictionary containing user profile information.

    Raises:
        httpx.HTTPStatusError: When Google returns a non-2xx response.
    """
    headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(GOOGLE_USERINFO_URL, headers=headers)
        response.raise_for_status()
        return response.json()


def build_authorization_url(state: str) -> str:
    """Public wrapper to build the Google OAuth authorization URL.

    Args:
        state: CSRF protection token.

    Returns:
        URL string for redirecting the user.
    """
    return _build_authorization_url(state)


async def fetch_user_info(code: str) -> OAuthUserInfo:
    """Complete OAuth flow: exchange code and fetch user info.

    Args:
        code: Authorization code from Google callback.

    Returns:
        Normalised OAuthUserInfo instance.
    """
    token_response: dict[str, Any] = await exchange_code_for_tokens(code)
    access_token: str = token_response["access_token"]
    profile: dict[str, Any] = await get_user_info(access_token)

    return OAuthUserInfo(
        provider=OAuthProvider.GOOGLE,
        provider_user_id=str(profile["id"]),
        email=profile["email"],
        name=profile.get("name"),
        avatar_url=profile.get("picture"),
    )
