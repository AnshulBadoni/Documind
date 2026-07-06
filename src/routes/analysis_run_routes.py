"""AnalysisRun routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from src.auth.oauth2 import get_current_user
from src.controllers.analysis_run_controller import AnalysisRunController
from src.database import get_db
from src.models.user_model import UserModel
from src.schemas.analysis_run_schema import AnalysisRunCreate

router = APIRouter(prefix="/projects/{project_id}/analysis-runs", tags=["Analysis Runs"])


@router.get("")
def get_analysis_runs(
    project_id: int,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """List all analysis runs for a project (ownership validated)."""
    controller = AnalysisRunController(db)
    return controller.get_analysis_runs(project_id=project_id, user_id=current_user.id)


@router.get("/{run_id}")
def get_analysis_run_by_id(
    project_id: int,
    run_id: int,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """Retrieve a single analysis run by ID (ownership validated)."""
    controller = AnalysisRunController(db)
    return controller.get_analysis_run_by_id(run_id=run_id, project_id=project_id, user_id=current_user.id)


@router.post("", status_code=201)
def create_analysis_run(
    project_id: int,
    background_tasks: BackgroundTasks,
    payload: AnalysisRunCreate | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """Create a new analysis run for a project."""
    if payload is None:
        payload = AnalysisRunCreate()
    controller = AnalysisRunController(db)
    return controller.create_analysis_run(
        project_id=project_id,
        payload=payload,
        user_id=current_user.id,
        background_tasks=background_tasks
    )
