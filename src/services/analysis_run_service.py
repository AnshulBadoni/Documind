"""AnalysisRun service — business logic and database access for analysis runs."""

import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.analysis_run_model import AnalysisRunModel, AnalysisStatus
from src.schemas.analysis_run_schema import AnalysisRunCreate


class AnalysisRunService:
    """Handles all analysis run-related business operations."""

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

    def get_analysis_run_by_id(self, run_id: int, project_id: int, user_id: int) -> AnalysisRunModel | None:
        """Retrieve a single analysis run with ownership validation.

        Args:
            run_id: Primary key of the analysis run.
            project_id: Parent project ID for authorization.
            user_id: Authenticated user's ID.

        Returns:
            AnalysisRunModel if found and authorized, else None.
        """
        if not self._verify_project_access(project_id, user_id):
            return None

        return (
            self.db.query(AnalysisRunModel)
            .filter(
                AnalysisRunModel.id == run_id,
                AnalysisRunModel.project_id == project_id,
            )
            .first()
        )

    def get_analysis_runs_for_project(self, project_id: int, user_id: int) -> list[AnalysisRunModel]:
        """Retrieve all analysis runs for a project owned by the user.

        Args:
            project_id: Parent project ID.
            user_id: Authenticated user's ID.

        Returns:
            List of AnalysisRunModel instances, or empty list if not authorized.
        """
        if not self._verify_project_access(project_id, user_id):
            return []

        return (
            self.db.query(AnalysisRunModel)
            .filter(AnalysisRunModel.project_id == project_id)
            .order_by(AnalysisRunModel.created_at.desc())
            .all()
        )

    def create_analysis_run(self, project_id: int, payload: AnalysisRunCreate, user_id: int) -> AnalysisRunModel:
        """Create a new analysis run.

        Args:
            project_id: Parent project ID.
            payload: Validated analysis run creation data.
            user_id: Authenticated user's ID (set as trigger).

        Returns:
            The newly created AnalysisRunModel instance.

        Raises:
            ValueError: When the project is not owned by the user.
            IntegrityError: On database constraint violations.
        """
        if not self._verify_project_access(project_id, user_id):
            raise ValueError("Project not found or access denied")

        from src.models.entry_model import EntryModel
        
        entry_id = payload.entry_id
        if not entry_id:
            entry = self.db.query(EntryModel).filter(EntryModel.project_id == project_id).first()
            if entry:
                entry_id = entry.id

        analysis_run = AnalysisRunModel(
            project_id=project_id,
            entry_id=entry_id,
            status=AnalysisStatus.PENDING,
            triggered_by=user_id,
            started_at=datetime.datetime.now(datetime.timezone.utc),
        )
        # Store force_regenerate attribute on the model instance (or dynamically attach it)
        setattr(analysis_run, "force_regenerate", payload.force_regenerate)
        try:
            self.db.add(analysis_run)
            self.db.commit()
            self.db.refresh(analysis_run)
        except IntegrityError:
            self.db.rollback()
            raise
        return analysis_run

    def update_analysis_run_status(
        self,
        run_id: int,
        project_id: int,
        user_id: int,
        status: AnalysisStatus,
        error_message: str | None = None,
    ) -> AnalysisRunModel | None:
        """Update the status of an analysis run.

        Args:
            run_id: Primary key of the analysis run.
            project_id: Parent project ID for authorization.
            user_id: Authenticated user's ID.
            status: New status to set.
            error_message: Optional error message for failed/cancelled runs.

        Returns:
            Updated AnalysisRunModel instance, or None if not found/authorized.
        """
        run = self.get_analysis_run_by_id(run_id, project_id, user_id)
        if not run:
            return None

        run.status = status
        if error_message:
            run.error_message = error_message
        if status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED, AnalysisStatus.CANCELLED):
            run.completed_at = datetime.datetime.now(datetime.timezone.utc)
            if run.started_at:
                run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

        self.db.commit()
        self.db.refresh(run)
        return run
