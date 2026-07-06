"""Database engine and session management."""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_settings

settings = get_settings()

# Normalize common PostgreSQL URL variants so SQLAlchemy loads the correct dialect.
# - Aiven and some providers may supply URLs starting with `postgres://` (deprecated).
# - Mistaken values like `postgres+psycopg2://` (missing 'ql') will also fail.
# Convert them to `postgresql://` or `postgresql+<driver>://` as appropriate.
db_url = settings.database_url
if isinstance(db_url, str):
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    elif db_url.startswith("postgres+"):
        # e.g. "postgres+psycopg2://..." -> "postgresql+psycopg2://..."
        db_url = db_url.replace("postgres+", "postgresql+", 1)

engine = create_engine(db_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables in the database and run migrations."""
    from src.models.project_share_model import ProjectShareModel
    Base.metadata.create_all(bind=engine)
    from sqlalchemy import text
    with engine.begin() as conn:
        try:
            if not db_url.startswith("sqlite"):
                conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS sources TEXT;"))
                conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS model_name VARCHAR(100);"))
                conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS project_type VARCHAR(50);"))
                conn.execute(text("ALTER TABLE code_documents ALTER COLUMN embedding TYPE vector(4096);"))
            else:
                for col_sql in [
                    "ALTER TABLE chat_messages ADD COLUMN sources TEXT;",
                    "ALTER TABLE chat_messages ADD COLUMN model_name VARCHAR(100);",
                    "ALTER TABLE projects ADD COLUMN project_type VARCHAR(50);"
                ]:
                    try:
                        conn.execute(text(col_sql))
                    except Exception:
                        pass # Ignore if column already exists in SQLite
        except Exception as e:
            print(f"Migration error: {e}")
