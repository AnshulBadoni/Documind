"""ChatMessage ORM model."""

import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

class ChatMessageModel(Base):
    """ChatMessage table definition."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(255), default="default", index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # "user" or "assistant"
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[str] = mapped_column(Text, nullable=True)  # Comma-separated list of sources
    model_name: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.datetime.now(datetime.timezone.utc)
    )

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"<ChatMessageModel(id={self.id}, project_id={self.project_id}, session_id='{self.session_id}', role='{self.role}')>"
