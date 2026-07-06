"""Project controller — handles response formatting for project endpoints."""

from typing import Any
from sqlalchemy.orm import Session

from src.models.project_model import ProjectModel
from src.schemas.project_schema import ProjectCreate, ProjectUpdate
from src.services.project_service import ProjectService
from src.services.DTO import ResponseDto


def _project_to_dict(project: ProjectModel) -> dict:
    """Convert a ProjectModel to a serialisable dictionary.

    Args:
        project: SQLAlchemy model instance.

    Returns:
        Dictionary with project attributes suitable for JSON response.
    """
    repo_url = None
    entry_files = None
    if project.entries:
        repo_url = project.entries[0].repository_url
        if project.entries[0].entry_point_files:
            entry_files = [f.strip() for f in project.entries[0].entry_point_files.split(",")]

    excluded = [exc.pattern for exc in project.exclusions] if project.exclusions else None

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "owner_id": project.owner_id,
        "repository_url": repo_url,
        "entry_point_files": entry_files,
        "excluded_paths": excluded,
        "project_type": project.project_type,
        "stats": project.stats,
        "technology_stack": project.technology_stack,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }


class ProjectController:
    """Orchestrates project operations and formats responses."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session.

        Args:
            db: SQLAlchemy session instance.
        """
        self.service = ProjectService(db)

    def get_project_by_id(self, project_id: int, user_id: int) -> dict:
        """Retrieve a single project (ownership validated).

        Args:
            project_id: Primary key of the project.
            user_id: Authenticated user's ID.

        Returns:
            Formatted response dictionary.
        """
        try:
            project: ProjectModel | None = self.service.get_project_by_id(project_id, user_id)
            if project is None:
                return ResponseDto.fail(status=404, message="Project not found")
            return ResponseDto.ok(
                status=200,
                message="Project retrieved successfully",
                data=_project_to_dict(project),
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def get_projects(self, user_id: int) -> dict:
        """Retrieve all projects for the authenticated user.

        Args:
            user_id: Authenticated user's ID.

        Returns:
            Formatted response dictionary with list of projects.
        """
        try:
            projects: list[ProjectModel] = self.service.get_projects_for_user(user_id)
            return ResponseDto.ok(
                status=200,
                message="Projects retrieved successfully",
                data=[_project_to_dict(p) for p in projects],
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def create_project(self, payload: ProjectCreate, user_id: int, background_tasks: Any = None) -> dict:
        """Create a new project owned by the authenticated user.

        Args:
            payload: Validated project creation data.
            user_id: Authenticated user's ID (set as owner).
            background_tasks: Optional background tasks coordinator.

        Returns:
            Formatted response dictionary with created project data.
        """
        try:
            project: ProjectModel = self.service.create_project(payload, user_id)

            # Kick off analysis in the background if a repo URL was provided
            if payload.repository_url and background_tasks is not None:
                from src.services.analysis_service import AnalysisService
                analysis_svc = AnalysisService(self.service.db)
                background_tasks.add_task(
                    analysis_svc.run_analysis,
                    project_id=project.id,
                    access_token=payload.access_token,
                )

            return ResponseDto.ok(
                status=201,
                message="Project created successfully.",
                data=_project_to_dict(project),
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def get_project_documents(self, project_id: int, user_id: int, include_chunks: bool = False) -> dict:
        """Retrieve all generated documents for a project (ownership validated)."""
        try:
            project = self.service.get_project_by_id(project_id, user_id)
            if not project:
                return ResponseDto.fail(status=404, message="Project not found or access denied")
            
            from src.models.code_document_model import CodeDocumentModel
            query = self.service.db.query(CodeDocumentModel).filter(
                CodeDocumentModel.project_id == project_id
            )
            
            if not include_chunks:
                query = query.filter(
                    CodeDocumentModel.document_type != "code_chunk",
                    CodeDocumentModel.document_type != "file_detail"
                )
                
            docs = query.all()
            
            formatted_docs = []
            for doc in docs:
                formatted_docs.append({
                    "id": doc.id,
                    "document_type": doc.document_type,
                    "title": doc.title,
                    "file_path": doc.file_path,
                    "content": doc.content,
                    "created_at": doc.created_at.isoformat()
                })
            
            return ResponseDto.ok(
                status=200,
                message="Project documents retrieved successfully",
                data=formatted_docs
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def regenerate_document(self, project_id: int, document_type: str, user_id: int, access_token: str | None = None) -> dict:
        """Regenerate a specific document type for a project (ownership validated)."""
        try:
            # Check ownership
            project = self.service.get_project_by_id(project_id, user_id)
            if not project:
                return ResponseDto.fail(status=404, message="Project not found or access denied")
            
            from src.services.analysis_service import AnalysisService
            analysis_svc = AnalysisService(self.service.db)
            doc = analysis_svc.regenerate_single_document(project_id, document_type, access_token)
            
            return ResponseDto.ok(
                status=200,
                message="Document regenerated successfully",
                data={
                    "id": doc.id,
                    "document_type": doc.document_type,
                    "title": doc.title,
                    "file_path": doc.file_path,
                    "content": doc.content,
                    "created_at": doc.created_at.isoformat()
                }
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def update_project(
        self, project_id: int, payload: ProjectUpdate, user_id: int
    ) -> dict:
        """Update project details (like project type)."""
        try:
            project = self.service.get_project_by_id(project_id, user_id)
            if not project:
                return ResponseDto.fail(status=404, message="Project not found")

            if payload.name is not None:
                project.name = payload.name
            if payload.description is not None:
                project.description = payload.description
            if payload.project_type is not None:
                project.project_type = payload.project_type

            self.service.db.add(project)
            self.service.db.commit()
            return ResponseDto.ok(
                status=200,
                message="Project updated successfully",
                data=_project_to_dict(project),
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def delete_project(self, project_id: int, user_id: int) -> dict:
        """Delete a project and its cascades. Enforces ownership."""
        try:
            success = self.service.delete_project(project_id, user_id)
            if not success:
                return ResponseDto.fail(
                    status=404, message="Project not found or unauthorized"
                )
            return ResponseDto.ok(
                status=200,
                message="Project and all related data deleted successfully",
                data={"project_id": project_id},
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def get_file_detail(self, project_id: int, file_path: str, user_id: int) -> dict:
        """Retrieve the details and reconstructed code content of a file. Enforces ownership."""
        try:
            project = self.service.get_project_by_id(project_id, user_id)
            if not project:
                return ResponseDto.fail(
                    status=404, message="Project not found or unauthorized"
                )

            from src.models.code_document_model import CodeDocumentModel

            # 1. Fetch file summary / details (with fallback for filename-only matches)
            detail_doc = (
                self.service.db.query(CodeDocumentModel)
                .filter(
                    CodeDocumentModel.project_id == project_id,
                    CodeDocumentModel.document_type == "file_detail",
                    (CodeDocumentModel.file_path == file_path) |
                    (CodeDocumentModel.file_path.like(f"%/{file_path}")) |
                    (CodeDocumentModel.file_path.like(f"%\\{file_path}"))
                )
                .first()
            )

            # Reconstruct exact path if found, otherwise fallback
            exact_path = detail_doc.file_path if detail_doc else file_path

            details_content = (
                detail_doc.content
                if detail_doc
                else "No summary details available for this file."
            )

            # 2. Fetch and join all code chunks
            chunk_docs = (
                self.service.db.query(CodeDocumentModel)
                .filter(
                    CodeDocumentModel.project_id == project_id,
                    CodeDocumentModel.document_type == "code_chunk",
                    CodeDocumentModel.file_path == exact_path,
                )
                .order_by(CodeDocumentModel.id.asc())
                .all()
            )

            reconstructed_code = (
                "".join([chunk.content for chunk in chunk_docs])
                if chunk_docs
                else ""
            )

            return ResponseDto.ok(
                status=200,
                message="File details retrieved successfully",
                data={
                    "file_path": file_path,
                    "details": details_content,
                    "code": reconstructed_code,
                },
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def share_project(self, project_id: int, owner_id: int, target_identity: str) -> dict:
        """Share a project with another user. Enforces ownership."""
        try:
            success = self.service.share_project(
                project_id=project_id,
                owner_id=owner_id,
                target_identity=target_identity
            )
            return ResponseDto.ok(
                status=200,
                message="Project shared successfully",
                data={"project_id": project_id, "shared_with": target_identity}
            )
        except ValueError as val_err:
            return ResponseDto.fail(status=400, message=str(val_err))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))
