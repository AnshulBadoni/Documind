"""User ORM model."""

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.oauth_model import OAuthAccountModel
    from src.models.project_model import ProjectModel


class UserModel(Base):
    """User table definition."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column("password_hash", String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    projects: Mapped[list["ProjectModel"]] = relationship("ProjectModel", back_populates="owner")
    oauth_accounts: Mapped[list["OAuthAccountModel"]] = relationship(
        "OAuthAccountModel", back_populates="user"
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<UserModel(id={self.id}, email='{self.email}')>"
