"""OAuth controller — handles response formatting for social login endpoints."""

from typing import Any

from sqlalchemy.orm import Session

from src.models.user_model import UserModel

from src.schemas.oauth_schema import OAuthCallbackRequest
from src.services.oauth_service import OAuthService
from src.services.DTO import ResponseDto
from src.config import get_settings


class OAuthController:
    """Orchestrates OAuth operations and formats responses."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session.

        Args:
            db: SQLAlchemy session instance.
        """
        self.service = OAuthService(db)
        self.settings = get_settings()

    def get_redirect_url(self, provider: str, state: str) -> dict[str, Any]:
        """Return the OAuth authorization URL for redirect.

        Args:
            provider: OAuth provider name ("google" or "github").
            state: CSRF protection token.

        Returns:
            Formatted response dictionary with redirect URL.
        """
        if provider == "google":
            from src.utils.oauth.google import build_authorization_url
            auth_url = build_authorization_url(state)
        elif provider == "github":
            from src.utils.oauth.github import build_authorization_url
            auth_url = build_authorization_url(state)
        else:
            return ResponseDto.fail(status=400, message=f"Unsupported provider: {provider}")

        return ResponseDto.ok(
            status=200,
            message="Redirect URL generated",
            data={"auth_url": auth_url, "state": state},
        )

    async def callback(self, provider: str, payload: OAuthCallbackRequest) -> dict[str, Any]:
        """Handle OAuth callback and authenticate the user.

        Args:
            provider: OAuth provider name ("google" or "github").
            payload: Callback data containing authorization code.

        Returns:
            Formatted response dictionary with JWT token on success.
        """
        try:
            if provider == "google":
                token_response = await self.service.authenticate_google(payload.code)
            elif provider == "github":
                token_response = await self.service.authenticate_github(payload.code)
            else:
                return ResponseDto.fail(status=400, message=f"Unsupported provider: {provider}")

            return ResponseDto.ok(
                status=200,
                message=f"Authenticated via {provider}",
                data={
                    "access_token": token_response.access_token,
                    "token_type": token_response.token_type,
                    "redirect_url": self.settings.oauth_success_redirect_url,
                },
            )
        except ValueError as exc:
            return ResponseDto.fail(status=400, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=f"OAuth authentication failed: {str(exc)}")

    def link_account(self, provider: str, payload: OAuthCallbackRequest, user: UserModel) -> dict[str, Any]:
        """Link an OAuth account to an existing authenticated user.

        Args:
            provider: OAuth provider name.
            payload: Callback data containing authorization code.
            user: The authenticated user.

        Returns:
            Formatted response dictionary with link status.
        """
        try:
            if provider == "google":
                result = self.service.link_google_account(user, payload.code)
            elif provider == "github":
                result = self.service.link_github_account(user, payload.code)
            else:
                return ResponseDto.fail(status=400, message=f"Unsupported provider: {provider}")

            return ResponseDto.ok(
                status=200,
                message=result.get("message", "Account linked"),
                data={"linked": result["linked"], "provider": provider},
            )
        except ValueError as exc:
            return ResponseDto.fail(status=409, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=f"Account linking failed: {str(exc)}")

    def unlink_account(self, provider: str, user: UserModel, db: Session) -> dict[str, Any]:
        """Unlink an OAuth account from an existing user.

        Args:
            provider: OAuth provider name.
            user: The authenticated user.
            db: Database session.

        Returns:
            Formatted response dictionary with unlink status.
        """
        from src.models.oauth_model import OAuthAccountModel

        try:
            oauth_account: OAuthAccountModel | None = (
                db.query(OAuthAccountModel)
                .filter(
                    OAuthAccountModel.user_id == user.id,
                    OAuthAccountModel.provider == provider,
                )
                .first()
            )

            if not oauth_account:
                return ResponseDto.fail(status=404, message=f"No {provider} account linked")

            db.delete(oauth_account)
            db.commit()

            return ResponseDto.ok(
                status=200,
                message=f"{provider} account unlinked successfully",
                data={"unlinked": True, "provider": provider},
            )
        except Exception as exc:
            db.rollback()
            return ResponseDto.fail(status=500, message=str(exc))
