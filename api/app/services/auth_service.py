from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import Settings
from api.app.core.security import (
    create_access_token,
    verify_password,
)
from api.app.models.user import User


class AuthenticationError(Exception):
    """Raised when supplied credentials are invalid."""


def user_by_email_query(email: str) -> Select[tuple[User]]:
    """Build the query for retrieving an active management user by email."""

    return select(User).where(User.email == email)


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    """Validate management credentials and return the matching user."""

    result = await session.execute(user_by_email_query(email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password")
    return user


def issue_user_token(settings: Settings, user: User) -> str:
    """Issue a JWT for an authenticated management user."""

    return create_access_token(
        settings,
        user_id=user.id,
        role=user.role,
        email=user.email,
    )
