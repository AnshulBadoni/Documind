"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Centralised settings loaded from environment variables / .env file."""

    app_name: str = "FastAPI Backend"
    debug: bool = False

    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/fastapi_db"
    )

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/auth/github/callback"

    # Frontend redirect after OAuth success
    oauth_success_redirect_url: str = "http://localhost:3000/dashboard"
    oauth_failure_redirect_url: str = "http://localhost:3000/login?error=auth_failed"

    # LLM Settings
    llm_provider: str = "nvidia"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    nvidia_api_key: str = ""
    nvidia_api_base: str = "https://integrate.api.nvidia.com/v1"
    pollinations_api_key: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a singleton Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
