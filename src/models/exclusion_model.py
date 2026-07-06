"""Exclusion ORM model."""

import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.entry_model import EntryModel
    from src.models.project_model import ProjectModel
    from src.models.user_model import UserModel

# Relationships refer to models by string names to avoid circular imports at runtime.


class ExclusionType(str, PyEnum):
    """Scope of an exclusion pattern."""

    PROJECT = "project"
    ENTRY = "entry"


class ExclusionModel(Base):
    """Exclusion table definition - patterns to exclude from analysis."""

    __tablename__ = "exclusions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("entries.id", ondelete="CASCADE"), nullable=True, index=True
    )
    pattern: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    exclusion_type: Mapped[ExclusionType] = mapped_column(
        Enum(ExclusionType), nullable=False, default=ExclusionType.PROJECT
    )
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )

    # Relationships
    project: Mapped["ProjectModel"] = relationship(
        "ProjectModel", back_populates="exclusions"
    )
    entry: Mapped["EntryModel"] = relationship(
        "EntryModel", back_populates="exclusions"
    )
    creator: Mapped["UserModel"] = relationship("UserModel")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<ExclusionModel(id={self.id}, pattern='{self.pattern}', type={self.exclusion_type.value})>"
