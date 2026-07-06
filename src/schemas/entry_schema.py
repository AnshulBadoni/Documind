"""Entry Pydantic schemas for request/response validation."""

import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EntryType(str, Enum):
    """Supported entry types matching the model."""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    LOCAL_UPLOAD = "local_upload"
    ZIP_FILE = "zip_file"


class EntryBase(BaseModel):
    """Shared attributes for creating and updating entries."""

    name: str = Field(..., min_length=1, max_length=255)
    repository_url: HttpUrl | None = None
    branch: str | None = Field(default=None, max_length=255)
    entry_type: EntryType = Field(default=EntryType.LOCAL_UPLOAD)


class EntryCreate(EntryBase):
    """Schema for entry creation requests."""

    pass


class EntryUpdate(BaseModel):
    """Schema for partial entry updates."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    repository_url: HttpUrl | None = None
    branch: str | None = Field(default=None, max_length=255)
    entry_type: EntryType | None = None


class EntryResponse(EntryBase):
    """Schema returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_by: int | None
    created_at: datetime.datetime
