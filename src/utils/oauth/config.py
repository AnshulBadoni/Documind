"""OAuth utility configuration — provider enums and user info container."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OAuthProvider(str, Enum):
    GOOGLE = "google"
    GITHUB = "github"


@dataclass
class OAuthUserInfo:
    provider: OAuthProvider
    provider_user_id: str
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None
