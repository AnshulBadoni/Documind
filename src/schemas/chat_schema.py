"""Chat Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Schema for chat queries about the project's codebase."""

    message: str = Field(..., description="The query/question about the codebase")
    session_id: str = Field(default="default", description="Conversation session thread identifier")


class ChatResponse(BaseModel):
    """Schema for chat responses."""

    answer: str = Field(..., description="The generated response from the LLM based on codebase context")
    sources: list[str] = Field(default=[], description="List of source files or documents retrieved as context")
