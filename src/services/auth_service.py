"""Authentication service — business logic for auth."""

from sqlalchemy.orm import Session

from src.auth.jwt_handler import create_access_token
from src.auth.password import hash_password, verify_password
from src.models.user_model import UserModel
from src.schemas.auth_schema import LoginRequest, TokenResponse
from src.schemas.user_schema import UserCreate


class AuthService:
    """Handles all authentication-related business operations."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session.

        Args:
            db: SQLAlchemy session instance.
        """
        self.db = db

    def register_user(self, payload: UserCreate) -> UserModel:
        """Create a new user account.

        Args:
            payload: Validated user creation data.

        Returns:
            The newly created UserModel instance.

        Raises:
            ValueError: When the email is already registered.
        """
        existing: UserModel | None = (
            self.db.query(UserModel)
            .filter(UserModel.email == payload.email)
            .first()
        )
        if existing:
            raise ValueError("Email already registered")

        hashed_pw: str = hash_password(payload.password)
        username = payload.username or payload.email.split("@")[0]
        new_user: UserModel = UserModel(
            email=payload.email,
            username=username,
            hashed_password=hashed_pw,
        )
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user

    def authenticate_user(self, payload: LoginRequest) -> UserModel | None:
        """Verify user credentials.

        Args:
            payload: Login request containing email and password.

        Returns:
            UserModel if credentials are valid, None otherwise.
        """
        user: UserModel | None = (
            self.db.query(UserModel)
            .filter(UserModel.email == payload.email)
            .first()
        )
        if not user:
            return None
        if not verify_password(payload.password, user.hashed_password):
            return None
        return user

    def create_token(self, user: UserModel) -> TokenResponse:
        """Generate a JWT access token for an authenticated user.

        Args:
            user: The authenticated UserModel.

        Returns:
            TokenResponse containing the access token.
        """
        token_data: dict[str, int | str] = {"sub": str(user.id), "email": user.email, "username": user.username or ""}
        access_token: str = create_access_token(data=token_data)
        return TokenResponse(access_token=access_token, token_type="bearer")
