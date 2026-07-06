"""Project service — business logic and database access for projects."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.project_model import ProjectModel
from src.schemas.project_schema import ProjectCreate


class ProjectService:
    """Handles all project-related business operations."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session.

        Args:
            db: SQLAlchemy session instance.
        """
        self.db = db

    def get_project_by_id(self, project_id: int, user_id: int) -> ProjectModel | None:
        """Retrieve a single project owned by or shared with the given user."""
        from src.models.project_share_model import ProjectShareModel
        from sqlalchemy import or_
        return (
            self.db.query(ProjectModel)
            .outerjoin(ProjectShareModel, ProjectModel.id == ProjectShareModel.project_id)
            .filter(
                ProjectModel.id == project_id,
                or_(
                    ProjectModel.owner_id == user_id,
                    ProjectShareModel.user_id == user_id
                )
            )
            .first()
        )

    def get_projects_for_user(self, user_id: int) -> list[ProjectModel]:
        """Retrieve all projects owned by or shared with the given user."""
        from src.models.project_share_model import ProjectShareModel
        from sqlalchemy import or_
        return (
            self.db.query(ProjectModel)
            .outerjoin(ProjectShareModel, ProjectModel.id == ProjectShareModel.project_id)
            .filter(
                or_(
                    ProjectModel.owner_id == user_id,
                    ProjectShareModel.user_id == user_id
                )
            )
            .distinct()
            .order_by(ProjectModel.created_at.desc())
            .all()
        )

    def create_project(self, payload: ProjectCreate, user_id: int) -> ProjectModel:
        """Create a new project and assign ownership to the authenticated user.

        Args:
            payload: Validated project creation data.
            user_id: Authenticated user's ID (will be set as owner_id).

        Returns:
            The newly created ProjectModel instance.

        Raises:
            IntegrityError: When there is a database-level constraint violation.
        """
        from src.models.entry_model import EntryModel, EntryType
        from src.models.exclusion_model import ExclusionModel, ExclusionType

        new_project: ProjectModel = ProjectModel(
            name=payload.name,
            description=payload.description,
            owner_id=user_id,
        )
        try:
            self.db.add(new_project)
            self.db.commit()
            self.db.refresh(new_project)

            # Create EntryModel if repository_url is provided
            entry_id = None
            if payload.repository_url:
                entry_point_str = ", ".join(payload.entry_point_files) if payload.entry_point_files else None
                
                # Guess entry type from URL
                entry_type = EntryType.LOCAL_UPLOAD
                url_str = str(payload.repository_url).lower()
                if "github.com" in url_str:
                    entry_type = EntryType.GITHUB
                elif "gitlab.com" in url_str:
                    entry_type = EntryType.GITLAB
                elif "bitbucket.org" in url_str:
                    entry_type = EntryType.BITBUCKET

                new_entry = EntryModel(
                    project_id=new_project.id,
                    name=f"{payload.name} Main Repository",
                    repository_url=payload.repository_url,
                    entry_point_files=entry_point_str,
                    entry_type=entry_type,
                    created_by=user_id
                )
                self.db.add(new_entry)
                self.db.commit()
                self.db.refresh(new_entry)
                entry_id = new_entry.id

            # Create ExclusionModels if excluded_paths are provided
            if payload.excluded_paths:
                for path in payload.excluded_paths:
                    new_exclusion = ExclusionModel(
                        project_id=new_project.id,
                        entry_id=entry_id,
                        pattern=path,
                        exclusion_type=ExclusionType.PROJECT,
                        created_by=user_id
                    )
                    self.db.add(new_exclusion)
                self.db.commit()

        except IntegrityError:
            self.db.rollback()
            raise
        return new_project

    def delete_project(self, project_id: int, user_id: int) -> bool:
        """Delete a project and all its database cascades.

        Enforces strict ownership check (only original owner can delete).
        """
        project = (
            self.db.query(ProjectModel)
            .filter(
                ProjectModel.id == project_id,
                ProjectModel.owner_id == user_id
            )
            .first()
        )
        if not project:
            return False

        self.db.delete(project)
        self.db.commit()
        return True

    def share_project(self, project_id: int, owner_id: int, target_identity: str) -> bool:
        """Share a project with another user by their username or email."""
        # 1. Enforce that only the project owner can share it
        project = (
            self.db.query(ProjectModel)
            .filter(ProjectModel.id == project_id, ProjectModel.owner_id == owner_id)
            .first()
        )
        if not project:
            raise ValueError("Project not found or unauthorized")

        # 2. Find target user
        from src.models.user_model import UserModel
        target_user = (
            self.db.query(UserModel)
            .filter(
                (UserModel.username == target_identity) |
                (UserModel.email == target_identity)
            )
            .first()
        )
        if not target_user:
            raise ValueError("Target user not found")

        # Can't share with yourself
        if target_user.id == owner_id:
            raise ValueError("You cannot share a project with yourself")

        # 3. Check if already shared
        from src.models.project_share_model import ProjectShareModel
        existing_share = (
            self.db.query(ProjectShareModel)
            .filter(
                ProjectShareModel.project_id == project_id,
                ProjectShareModel.user_id == target_user.id
            )
            .first()
        )
        if existing_share:
            return True

        # 4. Create new share mapping
        new_share = ProjectShareModel(
            project_id=project_id,
            user_id=target_user.id
        )
        self.db.add(new_share)
        self.db.commit()
        return True
