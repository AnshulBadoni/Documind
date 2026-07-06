"""ProjectShare ORM model."""

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.database import Base

class ProjectShareModel(Base):
    """Project shares association table definition."""

    __tablename__ = "project_shares"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Relationships
    project: Mapped["ProjectModel"] = relationship("ProjectModel", back_populates="shares")
    user: Mapped["UserModel"] = relationship("UserModel")
