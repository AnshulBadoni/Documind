"""AnalysisRun ORM model."""

import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.models.entry_model import EntryModel
    from src.models.project_model import ProjectModel
    from src.models.user_model import UserModel

# Relationships refer to models by string names to avoid circular imports at runtime.


class AnalysisStatus(str, PyEnum):
    """Status values for an analysis run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisRunModel(Base):
    """AnalysisRun table definition - tracks execution history of analysis jobs."""

    __tablename__ = "analysis_runs"

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
        Integer,
        ForeignKey("entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus), nullable=False, default=AnalysisStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    triggered_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )

    # Relationships
    project: Mapped["ProjectModel"] = relationship(
        "ProjectModel", back_populates="analysis_runs"
    )
    entry: Mapped["EntryModel"] = relationship(
        "EntryModel", back_populates="analysis_runs"
    )
    trigger_user: Mapped["UserModel"] = relationship("UserModel")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<AnalysisRunModel(id={self.id}, status={self.status.value}, project_id={self.project_id})>"
