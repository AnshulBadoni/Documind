"""Project routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from src.auth.oauth2 import get_current_user
from src.controllers.project_controller import ProjectController
from src.database import get_db
from src.models.user_model import UserModel
from src.schemas.project_schema import ProjectCreate, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("")
def get_projects(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """List all projects owned by the authenticated user.

    Args:
        db: Injected database session.
        current_user: Authenticated user (from JWT).

    Returns:
        Formatted response dictionary with project list.
    """
    controller = ProjectController(db)
    return controller.get_projects(user_id=current_user.id)


@router.get("/{project_id}")
def get_project_by_id(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Retrieve a single project by ID (ownership validated).

    Args:
        project_id: Primary key of the project.
        db: Injected database session.
        current_user: Authenticated user (from JWT).

    Returns:
        Formatted response dictionary with project data.
    """
    controller = ProjectController(db)
    return controller.get_project_by_id(project_id=project_id, user_id=current_user.id)


@router.post("", status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    background_tasks: BackgroundTasks,
) -> dict:
    """Create a new project owned by the authenticated user."""
    # Daily creation limit check (except for whitelisted email)
    if current_user.email != "anshulbadoni@gmail.com":
        import datetime
        from src.models.project_model import ProjectModel
        limit_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        created_today = (
            db.query(ProjectModel)
            .filter(
                ProjectModel.owner_id == current_user.id,
                ProjectModel.created_at >= limit_time
            )
            .count()
        )
        if created_today >= 1:
            raise HTTPException(
                status_code=429,
                detail="Daily limit reached. You can only add 1 repository per day. Upgrade for unlimited access."
            )

    controller = ProjectController(db)
    return controller.create_project(payload=payload, user_id=current_user.id, background_tasks=background_tasks)


@router.get("/{project_id}/documents")
def get_project_documents(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    include_chunks: bool = False,
) -> dict:
    """Retrieve all generated documentation files for a project.

    Args:
        project_id: Primary key of the project.
        db: Injected database session.
        current_user: Authenticated user (from JWT).
        include_chunks: Whether to include raw code chunks and AST file details.

    Returns:
        Formatted response dictionary with documents list.
    """
    controller = ProjectController(db)
    return controller.get_project_documents(
        project_id=project_id,
        user_id=current_user.id,
        include_chunks=include_chunks
    )


@router.post("/{project_id}/documents/{document_type}/regenerate")
def regenerate_project_document(
    project_id: int,
    document_type: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
    access_token: str | None = None,
) -> dict:
    """Regenerate a specific document type for a project.

    Args:
        project_id: Primary key of the project.
        document_type: The type of the document to regenerate.
        db: Injected database session.
        current_user: Authenticated user.
        access_token: Optional access token to use for re-cloning.
    """
    controller = ProjectController(db)
    return controller.regenerate_document(
        project_id=project_id,
        document_type=document_type,
        user_id=current_user.id,
        access_token=access_token
    )


@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Update project details (like project type)."""
    controller = ProjectController(db)
    return controller.update_project(
        project_id=project_id,
        payload=payload,
        user_id=current_user.id
    )


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Delete a project and its cascades. Enforces ownership."""
    controller = ProjectController(db)
    res = controller.delete_project(project_id=project_id, user_id=current_user.id)
    if res.get("error"):
        raise HTTPException(status_code=res["status"], detail=res["message"])
    return res


@router.get("/{project_id}/files/detail")
def get_file_detail(
    project_id: int,
    file_path: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Retrieve the details and reconstructed code content of a file. Enforces ownership."""
    controller = ProjectController(db)
    res = controller.get_file_detail(
        project_id=project_id,
        file_path=file_path,
        user_id=current_user.id
    )
    if res.get("error"):
        raise HTTPException(status_code=res["status"], detail=res["message"])
    return res


from pydantic import BaseModel

class ProjectSharePayload(BaseModel):
    target_identity: str


@router.post("/{project_id}/share")
def share_project(
    project_id: int,
    payload: ProjectSharePayload,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> dict:
    """Share a project with another user by their username or email."""
    controller = ProjectController(db)
    res = controller.share_project(
        project_id=project_id,
        owner_id=current_user.id,
        target_identity=payload.target_identity
    )
    if res.get("error"):
        raise HTTPException(status_code=res["status"], detail=res["message"])
    return res
