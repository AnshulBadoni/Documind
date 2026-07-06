"""Reusable response Data Transfer Object."""

from typing import Any

from pydantic import BaseModel, Field


class ResponseDto(BaseModel):
    """Standardised API response envelope."""

    status: int = Field(..., description="HTTP-like status code")
    error: bool = Field(..., description="Whether the request resulted in an error")
    message: str = Field(..., description="Human-readable status message")
    data: Any | None = Field(default=None, description="Optional response payload")

    @classmethod
    def ok(cls, status: int, message: str, data: Any | None = None) -> dict[str, Any]:
        """Build a success response dictionary."""
        return cls(status=status, error=False, message=message, data=data).model_dump()

    @classmethod
    def fail(cls, status: int, message: str, data: Any | None = None) -> dict[str, Any]:
        """Build an error response dictionary."""
        return cls(status=status, error=True, message=message, data=data).model_dump()
