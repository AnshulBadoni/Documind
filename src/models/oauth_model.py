"""OAuth account linking model."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.user_model import UserModel


class OAuthAccountModel(Base):
    """Tracks which OAuth accounts are linked to which users."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider_user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    access_token: Mapped[str] = mapped_column(String(500), nullable=True)
    refresh_token: Mapped[str] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel", back_populates="oauth_accounts"
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return (
            f"<OAuthAccountModel(id={self.id}, user_id={self.user_id}, "
            f"provider='{self.provider}', provider_user_id='{self.provider_user_id}')>"
        )
