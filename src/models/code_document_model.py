"""CodeDocument ORM model for storing generated codebase documentation chunks and their embeddings."""

import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base, db_url

is_sqlite = isinstance(db_url, str) and db_url.startswith("sqlite")

if is_sqlite:
    from sqlalchemy import JSON
    VectorType = JSON
else:
    from pgvector.sqlalchemy import Vector
    VectorType = Vector(4096)


class CodeDocumentModel(Base):
    """Stores generated documentation pieces, architecture summaries, and vectors."""

    __tablename__ = "code_documents"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VectorType, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.datetime.now(datetime.timezone.utc)
    )

    # Relationship to project
    project = relationship("ProjectModel", back_populates="code_documents")

    def __repr__(self) -> str:
        """Return a developer-friendly string representation."""
        return f"<CodeDocumentModel(id={self.id}, type='{self.document_type}', path='{self.file_path}')>"
