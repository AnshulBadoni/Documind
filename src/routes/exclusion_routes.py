"""Exclusion routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.oauth2 import get_current_user
from src.controllers.exclusion_controller import ExclusionController
from src.database import get_db
from src.models.user_model import UserModel
from src.schemas.exclusion_schema import ExclusionCreate

router = APIRouter(prefix="/projects/{project_id}/exclusions", tags=["Exclusions"])


@router.get("")
def get_exclusions(
    project_id: int,
    entry_id: int | None = Query(default=None, description="Filter by entry ID"),
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """List all exclusions for a project (optionally filtered by entry)."""
    controller = ExclusionController(db)
    if entry_id is not None:
        return controller.get_exclusions_for_entry(project_id=project_id, entry_id=entry_id, user_id=current_user.id)
    return controller.get_exclusions(project_id=project_id, user_id=current_user.id)


@router.post("", status_code=201)
def create_exclusion(
    project_id: int,
    payload: ExclusionCreate,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """Create a new exclusion pattern for a project."""
    controller = ExclusionController(db)
    return controller.create_exclusion(project_id=project_id, payload=payload, user_id=current_user.id)


@router.delete("/{exclusion_id}")
def delete_exclusion(
    project_id: int,
    exclusion_id: int,
    db: Annotated[Session, Depends(get_db)] = None,
    current_user: Annotated[UserModel, Depends(get_current_user)] = None,
) -> dict:
    """Delete an exclusion pattern (ownership validated)."""
    controller = ExclusionController(db)
    return controller.delete_exclusion(exclusion_id=exclusion_id, project_id=project_id, user_id=current_user.id)
