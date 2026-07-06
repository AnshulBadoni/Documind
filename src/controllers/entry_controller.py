"""Entry controller — handles response formatting for entry endpoints."""

from typing import Any

from sqlalchemy.orm import Session

from src.models.entry_model import EntryModel
from src.schemas.entry_schema import EntryCreate, EntryUpdate
from src.services.entry_service import EntryService
from src.services.DTO import ResponseDto


def _entry_to_dict(entry: EntryModel) -> dict[str, Any]:
    """Convert an EntryModel to a serialisable dictionary."""
    return {
        "id": entry.id,
        "project_id": entry.project_id,
        "name": entry.name,
        "repository_url": entry.repository_url,
        "branch": entry.branch,
        "entry_type": entry.entry_type.value if hasattr(entry.entry_type, "value") else entry.entry_type,
        "created_by": entry.created_by,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


class EntryController:
    """Orchestrates entry operations and formats responses."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session."""
        self.service = EntryService(db)

    def get_entries(self, project_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve all entries for a project (ownership validated)."""
        try:
            entries = self.service.get_entries_for_project(project_id, user_id)
            return ResponseDto.ok(
                status=200,
                message="Entries retrieved successfully",
                data=[_entry_to_dict(e) for e in entries],
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def get_entry_by_id(self, entry_id: int, project_id: int, user_id: int) -> dict[str, Any]:
        """Retrieve a single entry by ID (ownership validated)."""
        try:
            entry = self.service.get_entry_by_id(entry_id, project_id, user_id)
            if entry is None:
                return ResponseDto.fail(status=404, message="Entry not found")
            return ResponseDto.ok(
                status=200,
                message="Entry retrieved successfully",
                data=_entry_to_dict(entry),
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def create_entry(self, project_id: int, payload: EntryCreate, user_id: int) -> dict[str, Any]:
        """Create a new entry for a project."""
        try:
            entry = self.service.create_entry(project_id, payload, user_id)
            return ResponseDto.ok(
                status=201,
                message="Entry created successfully",
                data=_entry_to_dict(entry),
            )
        except ValueError as exc:
            return ResponseDto.fail(status=403, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def update_entry(
        self, entry_id: int, project_id: int, payload: EntryUpdate, user_id: int
    ) -> dict[str, Any]:
        """Update an existing entry."""
        try:
            entry = self.service.update_entry(entry_id, project_id, payload, user_id)
            if entry is None:
                return ResponseDto.fail(status=404, message="Entry not found")
            return ResponseDto.ok(
                status=200,
                message="Entry updated successfully",
                data=_entry_to_dict(entry),
            )
        except ValueError as exc:
            return ResponseDto.fail(status=403, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def delete_entry(self, entry_id: int, project_id: int, user_id: int) -> dict[str, Any]:
        """Delete an entry from a project."""
        try:
            deleted = self.service.delete_entry(entry_id, project_id, user_id)
            if not deleted:
                return ResponseDto.fail(status=404, message="Entry not found")
            return ResponseDto.ok(status=200, message="Entry deleted successfully")
        except ValueError as exc:
            return ResponseDto.fail(status=403, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))
