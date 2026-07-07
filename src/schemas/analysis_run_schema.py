"""AnalysisRun Pydantic schemas for request/response validation."""

import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AnalysisStatus(str, Enum):
    """Status values for an analysis run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisRunCreate(BaseModel):
    """Schema for creating a new analysis run."""

    entry_id: int | None = Field(default=None, description="Specific entry to analyze, or None for all entries")
    force_regenerate: bool = Field(default=False, description="Wipe existing documents and run a fresh analysis/regeneration")


class AnalysisRunUpdate(BaseModel):
    """Schema for updating an analysis run (e.g., cancel)."""

    status: AnalysisStatus | None = None


class AnalysisRunResponse(BaseModel):
    """Schema returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    entry_id: int | None
    status: AnalysisStatus
    error_message: str | None
    duration_seconds: float | None
    triggered_by: int | None
    started_at: datetime.datetime | None
    completed_at: datetime.datetime | None
    created_at: datetime.datetime
