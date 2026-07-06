"""Project ORM model."""

import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.models.analysis_run_model import AnalysisRunModel
from src.models.entry_model import EntryModel
from src.models.exclusion_model import ExclusionModel
from src.models.user_model import UserModel
from src.models.code_document_model import CodeDocumentModel

# Avoid importing other model modules here to prevent circular imports;
# relationships are declared using string names below.


class ProjectModel(Base):
    """Project table definition."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    technology_stack: Mapped[list | None] = mapped_column(JSON, nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.datetime.now(datetime.timezone.utc),
        onupdate=datetime.datetime.now(datetime.timezone.utc),
    )

    # Relationships
    owner: Mapped["UserModel"] = relationship("UserModel", back_populates="projects")
    entries: Mapped[list["EntryModel"]] = relationship(
        "EntryModel", back_populates="project", cascade="all, delete-orphan"
    )
    exclusions: Mapped[list["ExclusionModel"]] = relationship(
        "ExclusionModel", back_populates="project", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRunModel"]] = relationship(
        "AnalysisRunModel", back_populates="project", cascade="all, delete-orphan"
    )
    code_documents: Mapped[list["CodeDocumentModel"]] = relationship(
        "CodeDocumentModel", back_populates="project", cascade="all, delete-orphan"
    )
    shares: Mapped[list["ProjectShareModel"]] = relationship(
        "ProjectShareModel", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<ProjectModel(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"
