"""AnalysisRun controller — handles response formatting for analysis run endpoints."""

from typing import Any

from sqlalchemy.orm import Session

from src.models.analysis_run_model import AnalysisRunModel
from src.schemas.analysis_run_schema import AnalysisRunCreate
from src.services.analysis_run_service import AnalysisRunService
from src.services.DTO import ResponseDto


def _analysis_run_to_dict(run: AnalysisRunModel) -> dict[str, Any]:
    """Convert an AnalysisRunModel to a serialisable dictionary."""
    return {
        "id": run.id,
        "project_id": run.project_id,
        "entry_id": run.entry_id,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "error_message": run.error_message,
        "duration_seconds": run.duration_seconds,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


class AnalysisRunController:
    """Orchestrates analysis run operations and formats responses."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session."""
        self.service = AnalysisRunService(db)

    def get_analysis_runs(self, project_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve all analysis runs for a project."""
        try:
            runs = self.service.get_analysis_runs_for_project(project_id, user_id)
            return ResponseDto.ok(
                status=200,
                message="Analysis runs retrieved successfully",
                data=[_analysis_run_to_dict(r) for r in runs],
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def get_analysis_run_by_id(self, run_id: int, project_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve a single analysis run by ID."""
        try:
            run = self.service.get_analysis_run_by_id(run_id, project_id, user_id)
            if run is None:
                return ResponseDto.fail(status=404, message="Analysis run not found")
            return ResponseDto.ok(
                status=200,
                message="Analysis run retrieved successfully",
                data=_analysis_run_to_dict(run),
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def create_analysis_run(
        self, project_id: int, payload: AnalysisRunCreate, user_id: int, background_tasks: Any = None
    ) -> dict[str, Any]:
        """Create a new analysis run."""
        try:
            run = self.service.create_analysis_run(project_id, payload, user_id)
            if background_tasks and run.entry_id:
                from src.services.analysis_service import AnalysisService
                analyzer = AnalysisService(self.service.db)
                background_tasks.add_task(
                    analyzer.run_analysis,
                    project_id,
                    run.entry_id,
                    None,
                    payload.force_regenerate
                )
            return ResponseDto.ok(
                status=201,
                message="Analysis run created successfully. Analysis started in background.",
                data=_analysis_run_to_dict(run),
            )
        except ValueError as exc:
            return ResponseDto.fail(status=403, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def update_analysis_run_status(
        self, run_id: int, project_id: int, user_id: int, status: str, error_message: str | None = None
    ) -> dict[str, Any]:
        """Update the status of an analysis run."""
        from src.models.analysis_run_model import AnalysisStatus

        try:
            try:
                analysis_status = AnalysisStatus(status)
            except ValueError:
                return ResponseDto.fail(
                    status=400,
                    message=f"Invalid status. Must be one of: {', '.join(s.value for s in AnalysisStatus)}",
                )

            run = self.service.update_analysis_run_status(run_id, project_id, user_id, analysis_status, error_message)
            if run is None:
                return ResponseDto.fail(status=404, message="Analysis run not found")
            return ResponseDto.ok(
                status=200,
                message="Analysis run status updated successfully",
                data=_analysis_run_to_dict(run),
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))
