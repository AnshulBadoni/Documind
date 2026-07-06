"""Entry service — business logic and database access for entries."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.entry_model import EntryModel
from src.schemas.entry_schema import EntryCreate, EntryUpdate


class EntryService:
    """Handles all entry-related business operations."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session."""
        self.db = db

    def get_entry_by_id(self, entry_id: int, project_id: int, user_id: int) -> EntryModel | None:
        """Retrieve a single entry with ownership validation.

        Validates that the project belongs to the user before returning the entry.

        Args:
            entry_id: Primary key of the entry.
            project_id: Parent project ID for authorization.
            user_id: Authenticated user's ID.

        Returns:
            EntryModel if found and authorized, else None.
        """
        from src.models.project_model import ProjectModel

        project = (
            self.db.query(ProjectModel)
            .filter(ProjectModel.id == project_id, ProjectModel.owner_id == user_id)
            .first()
        )
        if not project:
            return None

        return (
            self.db.query(EntryModel)
            .filter(EntryModel.id == entry_id, EntryModel.project_id == project_id)
            .first()
        )

    def get_entries_for_project(self, project_id: int, user_id: int) -> list[EntryModel]:
        """Retrieve all entries for a project owned by the user.

        Args:
            project_id: Parent project ID.
            user_id: Authenticated user's ID.

        Returns:
            List of EntryModel instances.
        """
        from src.models.project_model import ProjectModel

        project = (
            self.db.query(ProjectModel)
            .filter(ProjectModel.id == project_id, ProjectModel.owner_id == user_id)
            .first()
        )
        if not project:
            return []

        return (
            self.db.query(EntryModel)
            .filter(EntryModel.project_id == project_id)
            .order_by(EntryModel.created_at.desc())
            .all()
        )

    def create_entry(self, project_id: int, payload: EntryCreate, user_id: int) -> EntryModel:
        """Create a new entry for a project.

        Args:
            project_id: Parent project ID.
            payload: Validated entry creation data.
            user_id: Authenticated user's ID (set as creator).

        Returns:
            The newly created EntryModel instance.

        Raises:
            ValueError: When the project is not owned by the user.
            IntegrityError: On database constraint violations.
        """
        from src.models.project_model import ProjectModel

        project = (
            self.db.query(ProjectModel)
            .filter(ProjectModel.id == project_id, ProjectModel.owner_id == user_id)
            .first()
        )
        if not project:
            raise ValueError("Project not found or access denied")

        entry = EntryModel(
            project_id=project_id,
            name=payload.name,
            repository_url=str(payload.repository_url) if payload.repository_url else None,
            branch=payload.branch,
            entry_type=payload.entry_type,
            created_by=user_id,
        )
        try:
            self.db.add(entry)
            self.db.commit()
            self.db.refresh(entry)
        except IntegrityError:
            self.db.rollback()
            raise
        return entry

    def update_entry(self, entry_id: int, project_id: int, payload: EntryUpdate, user_id: int) -> EntryModel | None:
        """Update an existing entry.

        Args:
            entry_id: Primary key of the entry.
            project_id: Parent project ID for authorization.
            payload: Validated entry update data.
            user_id: Authenticated user's ID.

        Returns:
            Updated EntryModel instance, or None if not found/authorized.

        Raises:
            ValueError: When the project is not owned by the user.
        """
        from src.models.project_model import ProjectModel

        project = (
            self.db.query(ProjectModel)
            .filter(ProjectModel.id == project_id, ProjectModel.owner_id == user_id)
            .first()
        )
        if not project:
            raise ValueError("Project not found or access denied")

        entry = self.get_entry_by_id(entry_id, project_id, user_id)
        if not entry:
            return None

        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                if key == "repository_url":
                    setattr(entry, key, str(value))
                else:
                    setattr(entry, key, value)

        self.db.commit()
        self.db.refresh(entry)
        return entry

    def delete_entry(self, entry_id: int, project_id: int, user_id: int) -> bool:
        """Delete an entry from a project.

        Args:
            entry_id: Primary key of the entry.
            project_id: Parent project ID for authorization.
            user_id: Authenticated user's ID.

        Returns:
            True if deleted, False if not found/authorized.

        Raises:
            ValueError: When the project is not owned by the user.
        """
        entry = self.get_entry_by_id(entry_id, project_id, user_id)
        if not entry:
            return False

        self.db.delete(entry)
        self.db.commit()
        return True
