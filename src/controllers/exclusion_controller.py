"""Exclusion controller — handles response formatting for exclusion endpoints."""

from typing import Any

from sqlalchemy.orm import Session

from src.models.exclusion_model import ExclusionModel
from src.schemas.exclusion_schema import ExclusionCreate
from src.services.exclusion_service import ExclusionService
from src.services.DTO import ResponseDto


def _exclusion_to_dict(exclusion: ExclusionModel) -> dict[str, Any]:
    """Convert an ExclusionModel to a serialisable dictionary."""
    return {
        "id": exclusion.id,
        "project_id": exclusion.project_id,
        "entry_id": exclusion.entry_id,
        "pattern": exclusion.pattern,
        "exclusion_type": exclusion.exclusion_type.value
        if hasattr(exclusion.exclusion_type, "value")
        else exclusion.exclusion_type,
        "created_by": exclusion.created_by,
        "created_at": exclusion.created_at.isoformat() if exclusion.created_at else None,
    }


class ExclusionController:
    """Orchestrates exclusion operations and formats responses."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session."""
        self.service = ExclusionService(db)

    def get_exclusions(self, project_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve all exclusions for a project."""
        try:
            exclusions = self.service.get_exclusions_for_project(project_id, user_id)
            return ResponseDto.ok(
                status=200,
                message="Exclusions retrieved successfully",
                data=[_exclusion_to_dict(e) for e in exclusions],
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def get_exclusions_for_entry(self, project_id: int, entry_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve all exclusions for a specific entry."""
        try:
            exclusions = self.service.get_exclusions_for_entry(project_id, entry_id, user_id)
            return ResponseDto.ok(
                status=200,
                message="Entry exclusions retrieved successfully",
                data=[_exclusion_to_dict(e) for e in exclusions],
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def create_exclusion(self, project_id: int, payload: ExclusionCreate, user_id: int) -> dict[str, Any]:
        """Create a new exclusion pattern."""
        try:
            exclusion = self.service.create_exclusion(project_id, payload, user_id)
            return ResponseDto.ok(
                status=201,
                message="Exclusion created successfully",
                data=_exclusion_to_dict(exclusion),
            )
        except ValueError as exc:
            return ResponseDto.fail(status=403, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def delete_exclusion(self, exclusion_id: int, project_id: int, user_id: int) -> dict[str, Any]:
        """Delete an exclusion pattern."""
        try:
            deleted = self.service.delete_exclusion(exclusion_id, project_id, user_id)
            if not deleted:
                return ResponseDto.fail(status=404, message="Exclusion not found")
            return ResponseDto.ok(status=200, message="Exclusion deleted successfully")
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))
