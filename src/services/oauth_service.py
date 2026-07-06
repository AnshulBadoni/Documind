"""OAuth service — handles social login business logic."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.oauth_model import OAuthAccountModel
from src.models.user_model import UserModel
from src.schemas.auth_schema import TokenResponse
from src.utils.auth.jwt import create_access_token
from src.utils.oauth.config import OAuthProvider, OAuthUserInfo
from src.utils.oauth.google import (
    exchange_code_for_tokens as google_exchange_code,
    fetch_user_info as google_fetch_user_info,
)
from src.utils.oauth.github import (
    exchange_code_for_tokens as github_exchange_code,
    fetch_user_info as github_fetch_user_info,
)


class OAuthService:
    """Handles OAuth authentication and account linking."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session.

        Args:
            db: SQLAlchemy session instance.
        """
        self.db = db
        self.settings = get_settings()

    def _get_or_create_user(self, user_info: OAuthUserInfo) -> UserModel:
        """Find existing user or create a new one from OAuth info.

        Args:
            user_info: Normalised OAuth user information.

        Returns:
            Existing or newly created UserModel.
        """
        user: UserModel | None = (
            self.db.query(UserModel)
            .filter(UserModel.email == user_info.email)
            .first()
        )

        if not user:
            user = UserModel(email=user_info.email, is_active=True)
            self.db.add(user)
            self.db.flush()

        return user

    def _get_or_create_oauth_account(
        self, user: UserModel, user_info: OAuthUserInfo, token_response: dict[str, Any]
    ) -> OAuthAccountModel:
        """Find or create an OAuth account linking entry.

        Args:
            user: The user to link the OAuth account to.
            user_info: Normalised OAuth user information.
            token_response: Raw token response from the provider.

        Returns:
            Existing or newly created OAuthAccountModel.
        """
        oauth_account: OAuthAccountModel | None = (
            self.db.query(OAuthAccountModel)
            .filter(
                OAuthAccountModel.provider == user_info.provider.value,
                OAuthAccountModel.provider_user_id == user_info.provider_user_id,
            )
            .first()
        )

        if not oauth_account:
            oauth_account = OAuthAccountModel(
                user_id=user.id,
                provider=user_info.provider.value,
                provider_user_id=user_info.provider_user_id,
                access_token=token_response.get("access_token"),
                refresh_token=token_response.get("refresh_token"),
            )
            self.db.add(oauth_account)
            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                oauth_account = (
                    self.db.query(OAuthAccountModel)
                    .filter(
                        OAuthAccountModel.provider == user_info.provider.value,
                        OAuthAccountModel.provider_user_id == user_info.provider_user_id,
                    )
                    .first()
                )

        return oauth_account

    async def authenticate_google(self, code: str) -> TokenResponse:
        """Authenticate a user via Google OAuth.

        Args:
            code: Authorization code from Google callback.

        Returns:
            TokenResponse with JWT access token.
        """
        user_info: OAuthUserInfo = await google_fetch_user_info(code)
        token_response: dict[str, Any] = await google_exchange_code(code)
        return await self._authenticate_with_provider(user_info, token_response)

    async def authenticate_github(self, code: str) -> TokenResponse:
        """Authenticate a user via GitHub OAuth.

        Args:
            code: Authorization code from GitHub callback.

        Returns:
            TokenResponse with JWT access token.
        """
        user_info: OAuthUserInfo = await github_fetch_user_info(code)
        token_response: dict[str, Any] = await github_exchange_code(code)
        return await self._authenticate_with_provider(user_info, token_response)

    async def _authenticate_with_provider(
        self, user_info: OAuthUserInfo, token_response: dict[str, Any]
    ) -> TokenResponse:
        """Generic OAuth authentication flow for any provider.

        Args:
            user_info: Normalised OAuth user information.
            token_response: Token response from the provider.

        Returns:
            TokenResponse with JWT access token.
        """
        user: UserModel = self._get_or_create_user(user_info)
        self._get_or_create_oauth_account(user, user_info, token_response)
        self.db.commit()
        self.db.refresh(user)

        jwt_data: dict[str, Any] = {"sub": str(user.id), "email": user.email}
        access_token: str = create_access_token(data=jwt_data)

        return TokenResponse(access_token=access_token, token_type="bearer")

    def link_google_account(self, user: UserModel, code: str) -> dict[str, Any]:
        """Link a Google OAuth account to an existing user.

        Args:
            user: The authenticated user to link the account to.
            code: Authorization code from Google callback.

        Returns:
            Dictionary with link status.
        """
        user_info: OAuthUserInfo = google_fetch_user_info(code)
        return self._link_account(user, user_info)

    def link_github_account(self, user: UserModel, code: str) -> dict[str, Any]:
        """Link a GitHub OAuth account to an existing user.

        Args:
            user: The authenticated user to link the account to.
            code: Authorization code from GitHub callback.

        Returns:
            Dictionary with link status.
        """
        user_info: OAuthUserInfo = github_fetch_user_info(code)
        return self._link_account(user, user_info)

    def _link_account(self, user: UserModel, user_info: OAuthUserInfo) -> dict[str, Any]:
        """Generic account linking flow for any provider.

        Args:
            user: The authenticated user.
            user_info: Normalised OAuth user information.

        Returns:
            Dictionary with link status.

        Raises:
            ValueError: When the account is already linked.
        """
        existing: OAuthAccountModel | None = (
            self.db.query(OAuthAccountModel)
            .filter(
                OAuthAccountModel.provider == user_info.provider.value,
                OAuthAccountModel.provider_user_id == user_info.provider_user_id,
            )
            .first()
        )

        if existing:
            if existing.user_id == user.id:
                return {"linked": True, "message": "Account already linked"}
            raise ValueError("OAuth account already linked to a different user")

        oauth_account: OAuthAccountModel = OAuthAccountModel(
            user_id=user.id,
            provider=user_info.provider.value,
            provider_user_id=user_info.provider_user_id,
        )
        self.db.add(oauth_account)
        self.db.commit()
        self.db.refresh(oauth_account)

        return {"linked": True, "message": f"{user_info.provider.value} account linked successfully"}
