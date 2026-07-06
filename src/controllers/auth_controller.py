"""Auth controller — handles response formatting for auth endpoints."""

from sqlalchemy.orm import Session

from src.schemas.auth_schema import LoginRequest
from src.schemas.user_schema import UserCreate
from src.services.auth_service import AuthService
from src.services.DTO import ResponseDto


class AuthController:
    """Orchestrates auth operations and formats responses."""

    def __init__(self, db: Session) -> None:
        """Initialise with an injected database session.

        Args:
            db: SQLAlchemy session instance.
        """
        self.service = AuthService(db)

    def register_user(self, payload: UserCreate) -> dict:
        """Register a new user and return a formatted response.

        Args:
            payload: Validated user creation data.

        Returns:
            Formatted response dictionary via ResponseDto.
        """
        try:
            user = self.service.register_user(payload)
            return ResponseDto.ok(
                status=201,
                message="User registered successfully",
                data={"id": user.id, "email": user.email, "username": user.username or ""},
            )
        except ValueError as exc:
            return ResponseDto.fail(status=409, message=str(exc))
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))

    def login(self, payload: LoginRequest) -> dict:
        """Authenticate a user and return a JWT token.

        Args:
            payload: Validated login request.

        Returns:
            Formatted response dictionary with access token on success.
        """
        try:
            user = self.service.authenticate_user(payload)
            if not user:
                return ResponseDto.fail(status=401, message="Invalid credentials")

            token_response = self.service.create_token(user)
            return ResponseDto.ok(
                status=200,
                message="Login successful",
                data={
                    "access_token": token_response.access_token,
                    "token_type": token_response.token_type,
                    "username": user.username or "",
                },
            )
        except Exception as exc:
            return ResponseDto.fail(status=500, message=str(exc))
