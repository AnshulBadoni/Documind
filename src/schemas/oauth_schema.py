"""OAuth schemas for request/response validation."""

from pydantic import BaseModel, Field


class OAuthCallbackRequest(BaseModel):
    """Schema for OAuth callback query parameters."""

    code: str = Field(..., description="Authorization code from the provider")
    state: str | None = Field(
        default=None, description="State parameter for CSRF protection"
    )


class OAuthRedirectResponse(BaseModel):
    """Schema returned when redirecting to an OAuth provider."""

    auth_url: str = Field(
        ..., description="URL to redirect the user to for authorization"
    )
    state: str | None = Field(default=None, description="CSRF state token echoed back")


class OAuthLinkResponse(BaseModel):
    """Schema returned when linking an OAuth account to an existing user."""

    linked: bool = Field(
        ..., description="Whether the OAuth account was linked successfully"
    )
    provider: str = Field(..., description="OAuth provider name")
