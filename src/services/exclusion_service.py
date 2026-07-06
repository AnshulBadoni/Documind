"""Exclusion service — business logic and database access for exclusions."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.exclusion_model import ExclusionModel
from src.schemas.exclusion_schema import ExclusionCreate


class ExclusionService:
    """Handles all exclusion-related business operations."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session."""
        self.db = db

    def _verify_project_access(self, project_id: int, user_id: int) -> bool:
        """Verify that the user owns the project.

        Args:
            project_id: Project to check.
            user_id: Authenticated user's ID.

        Returns:
            True if the user owns the project, False otherwise.
        """
        from src.models.project_model import ProjectModel

        project = (
            self.db.query(ProjectModel)
            .filter(ProjectModel.id == project_id, ProjectModel.owner_id == user_id)
            .first()
        )
        return project is not None

    def get_exclusions_for_project(self, project_id: int, user_id: int) -> list[ExclusionModel]:
        """Retrieve all exclusions for a project (both project-level and entry-level).

        Args:
            project_id: Parent project ID.
            user_id: Authenticated user's ID.

        Returns:
            List of ExclusionModel instances, or empty list if not authorized.
        """
        if not self._verify_project_access(project_id, user_id):
            return []

        return (
            self.db.query(ExclusionModel)
            .filter(ExclusionModel.project_id == project_id)
            .order_by(ExclusionModel.created_at.desc())
            .all()
        )

    def get_exclusions_for_entry(self, project_id: int, entry_id: int, user_id: int) -> list[ExclusionModel]:
        """Retrieve all exclusions for a specific entry within a project.

        Args:
            project_id: Parent project ID.
            entry_id: Entry to get exclusions for.
            user_id: Authenticated user's ID.

        Returns:
            List of ExclusionModel instances, or empty list if not authorized.
        """
        if not self._verify_project_access(project_id, user_id):
            return []

        return (
            self.db.query(ExclusionModel)
            .filter(
                ExclusionModel.project_id == project_id,
                ExclusionModel.entry_id == entry_id,
            )
            .order_by(ExclusionModel.created_at.desc())
            .all()
        )

    def create_exclusion(self, project_id: int, payload: ExclusionCreate, user_id: int) -> ExclusionModel:
        """Create a new exclusion pattern.

        Args:
            project_id: Parent project ID.
            payload: Validated exclusion creation data.
            user_id: Authenticated user's ID (set as creator).

        Returns:
            The newly created ExclusionModel instance.

        Raises:
            ValueError: When the project is not owned by the user.
            IntegrityError: On database constraint violations.
        """
        if not self._verify_project_access(project_id, user_id):
            raise ValueError("Project not found or access denied")

        exclusion = ExclusionModel(
            project_id=project_id,
            entry_id=payload.entry_id,
            pattern=payload.pattern,
            exclusion_type=payload.exclusion_type,
            created_by=user_id,
        )
        try:
            self.db.add(exclusion)
            self.db.commit()
            self.db.refresh(exclusion)
        except IntegrityError:
            self.db.rollback()
            raise
        return exclusion

    def delete_exclusion(self, exclusion_id: int, project_id: int, user_id: int) -> bool:
        """Delete an exclusion pattern.

        Args:
            exclusion_id: Primary key of the exclusion.
            project_id: Parent project ID for authorization.
            user_id: Authenticated user's ID.

        Returns:
            True if deleted, False if not found/authorized.
        """
        if not self._verify_project_access(project_id, user_id):
            return False

        exclusion = (
            self.db.query(ExclusionModel)
            .filter(
                ExclusionModel.id == exclusion_id,
                ExclusionModel.project_id == project_id,
            )
            .first()
        )
        if not exclusion:
            return False

        self.db.delete(exclusion)
        self.db.commit()
        return True
