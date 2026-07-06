"""GitHub OAuth2 client implementation."""

import httpx
from typing import Any

from src.config import get_settings
from src.utils.oauth.config import OAuthProvider, OAuthUserInfo


GITHUB_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL: str = "https://api.github.com/user"
GITHUB_EMAILS_URL: str = "https://api.github.com/user/emails"
GITHUB_AUTH_URL: str = "https://github.com/login/oauth/authorize"


def _build_authorization_url(state: str) -> str:
    """Build the GitHub OAuth authorization URL.

    Args:
        state: CSRF protection token.

    Returns:
        Fully-formed GitHub OAuth authorization URL.
    """
    settings = get_settings()
    params: dict[str, str] = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": "user:email",
        "state": state,
    }
    query: str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{GITHUB_AUTH_URL}?{query}"


async def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    """Exchange an authorization code for an access token.

    Args:
        code: Authorization code received from GitHub.

    Returns:
        Dictionary containing token response from GitHub.

    Raises:
        httpx.HTTPStatusError: When GitHub returns a non-2xx response.
    """
    settings = get_settings()
    payload: dict[str, str] = {
        "code": code,
        "client_id": settings.github_client_id,
        "client_secret": settings.github_client_secret,
        "redirect_uri": settings.github_redirect_uri,
    }
    headers: dict[str, str] = {"Accept": "application/json"}
    async with httpx.AsyncClient() as client:
        response = await client.post(GITHUB_TOKEN_URL, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()


async def get_user_info(access_token: str) -> dict[str, Any]:
    """Fetch user profile information from GitHub.

    Args:
        access_token: GitHub OAuth access token.

    Returns:
        Dictionary containing user profile information.

    Raises:
        httpx.HTTPStatusError: When GitHub returns a non-2xx response.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(GITHUB_USER_URL, headers=headers)
        response.raise_for_status()
        return response.json()


async def get_user_email(access_token: str) -> str:
    """Fetch the user's primary email from GitHub.

    Args:
        access_token: GitHub OAuth access token.

    Returns:
        The user's primary email address.

    Raises:
        ValueError: When no verified email is found.
        httpx.HTTPStatusError: When GitHub returns a non-2xx response.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(GITHUB_EMAILS_URL, headers=headers)
        response.raise_for_status()
        emails: list[dict[str, Any]] = response.json()

    for entry in emails:
        if entry.get("primary") and entry.get("verified"):
            return entry["email"]

    raise ValueError("No verified primary email found on GitHub account")


def build_authorization_url(state: str) -> str:
    """Public wrapper to build the GitHub OAuth authorization URL.

    Args:
        state: CSRF protection token.

    Returns:
        URL string for redirecting the user.
    """
    return _build_authorization_url(state)


async def fetch_user_info(code: str) -> OAuthUserInfo:
    """Complete OAuth flow: exchange code and fetch user info.

    Args:
        code: Authorization code from GitHub callback.

    Returns:
        Normalised OAuthUserInfo instance.
    """
    token_response: dict[str, Any] = await exchange_code_for_tokens(code)
    access_token: str = token_response["access_token"]

    profile: dict[str, Any] = await get_user_info(access_token)
    email: str = profile.get("email") or await get_user_email(access_token)

    return OAuthUserInfo(
        provider=OAuthProvider.GITHUB,
        provider_user_id=str(profile["id"]),
        email=email,
        name=profile.get("name") or profile.get("login"),
        avatar_url=profile.get("avatar_url"),
    )
