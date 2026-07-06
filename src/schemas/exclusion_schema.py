"""Exclusion Pydantic schemas for request/response validation."""

import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ExclusionType(str, Enum):
    """Scope of an exclusion pattern."""

    PROJECT = "project"
    ENTRY = "entry"


class ExclusionBase(BaseModel):
    """Shared attributes for creating exclusions."""

    pattern: str = Field(..., min_length=1, max_length=500)
    exclusion_type: ExclusionType = Field(default=ExclusionType.PROJECT)
    entry_id: int | None = None


class ExclusionCreate(ExclusionBase):
    """Schema for exclusion creation requests."""

    pass


class ExclusionResponse(ExclusionBase):
    """Schema returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int | None
    created_at: datetime.datetime
