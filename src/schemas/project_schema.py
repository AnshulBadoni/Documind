"""Project Pydantic schemas for request/response validation."""

import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    """Shared attributes for creating and updating projects."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    project_type: str | None = Field(default=None, max_length=50, description="Project type (e.g. backend, frontend, fullstack, ml_ai, mobile)")


class ProjectCreate(ProjectBase):
    """Schema for project creation requests."""

    repository_url: str | None = Field(default=None, description="Git repository URL to clone and analyze")
    access_token: str | None = Field(default=None, description="Personal access token for private repositories (not stored, used only during cloning)")
    entry_point_files: list[str] | None = Field(default=None, description="List of entry point files (e.g. server.ts, main.py)")
    excluded_paths: list[str] | None = Field(default=None, description="List of paths to exclude from analysis")


class ProjectUpdate(BaseModel):
    """Schema for partial project updates."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    project_type: str | None = Field(default=None, max_length=50)


class ProjectResponse(ProjectBase):
    """Schema returned in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    repository_url: str | None = None
    entry_point_files: list[str] | None = None
    excluded_paths: list[str] | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
