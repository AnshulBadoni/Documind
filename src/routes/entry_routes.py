"""Entry routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.oauth2 import get_current_user
from src.controllers.entry_controller import EntryController
from src.database import get_db
from src.models.user_model import UserModel
from src.schemas.entry_schema import EntryCreate, EntryUpdate

router = APIRouter(prefix="/projects/{project_id}/entries", tags=["Entries"])


@router.get("")
def get_entries(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """List all entries for a project (ownership validated)."""
    controller = EntryController(db)
    return controller.get_entries(project_id=project_id, user_id=current_user.id)


@router.get("/{entry_id}")
def get_entry(
    project_id: int,
    entry_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Retrieve a single entry by ID (ownership validated)."""
    controller = EntryController(db)
    return controller.get_entry_by_id(entry_id=entry_id, project_id=project_id, user_id=current_user.id)


@router.post("", status_code=201)
def create_entry(
    project_id: int,
    payload: EntryCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Create a new entry for a project.

    Ownership is validated before creation.
    """
    controller = EntryController(db)
    return controller.create_entry(project_id=project_id, payload=payload, user_id=current_user.id)


@router.patch("/{entry_id}")
def update_entry(
    project_id: int,
    entry_id: int,
    payload: EntryUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Update an existing entry (ownership validated)."""
    controller = EntryController(db)
    return controller.update_entry(entry_id=entry_id, project_id=project_id, payload=payload, user_id=current_user.id)


@router.delete("/{entry_id}")
def delete_entry(
    project_id: int,
    entry_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Delete an entry from a project (ownership validated)."""
    controller = EntryController(db)
    return controller.delete_entry(entry_id=entry_id, project_id=project_id, user_id=current_user.id)
