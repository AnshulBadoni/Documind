"""User Pydantic schemas for request/response validation."""

import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Shared attributes for user creation and response."""

    email: EmailStr = Field(..., max_length=255)


class UserCreate(UserBase):
    """Schema for user registration requests."""

    username: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseModel):
    """Schema for partial user updates."""

    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class UserResponse(UserBase):
    """Schema returned in API responses (excludes sensitive fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
