"""Entry ORM model."""

import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.exclusion_model import ExclusionModel
    from src.models.project_model import ProjectModel
    from src.models.user_model import UserModel
    from src.models.analysis_run_model import AnalysisRunModel

# Relationships refer to models by string names to avoid circular imports at runtime.


class EntryType(str, PyEnum):
    """Supported entry types for project analysis."""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    LOCAL_UPLOAD = "local_upload"
    ZIP_FILE = "zip_file"


class EntryModel(Base):
    """Entry table definition - represents something inside a project that can be analyzed."""

    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    repository_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entry_point_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_type: Mapped[EntryType] = mapped_column(
        Enum(EntryType), nullable=False, default=EntryType.LOCAL_UPLOAD
    )
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )

    # Relationships
    project: Mapped["ProjectModel"] = relationship(
        "ProjectModel", back_populates="entries"
    )
    creator: Mapped["UserModel"] = relationship("UserModel")
    exclusions: Mapped[list["ExclusionModel"]] = relationship(
        "ExclusionModel", back_populates="entry"
    )
    analysis_runs: Mapped[list["AnalysisRunModel"]] = relationship(
        "AnalysisRunModel", back_populates="entry"
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<EntryModel(id={self.id}, name='{self.name}', type={self.entry_type.value})>"
