"""Authentication dependencies — re-exports from utils.auth.current_user."""

from src.utils.auth.current_user import get_current_user, oauth2_scheme  # noqa: F401

__all__ = ["get_current_user", "oauth2_scheme"]
