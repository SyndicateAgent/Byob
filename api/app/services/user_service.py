from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.core.security import hash_password
from api.app.models.user import User
from api.app.schemas.user import UserCreateRequest, UserUpdateRequest


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user with an email that is already taken."""


async def list_users(session: AsyncSession) -> list[User]:
    """Return management users ordered by creation time."""

    result = await session.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    """Return a management user if present."""

    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    payload: UserCreateRequest,
) -> User:
    """Create a new management user with a hashed password."""

    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise UserAlreadyExistsError(payload.email) from exc
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    user: User,
    payload: UserUpdateRequest,
) -> User:
    """Update mutable user fields (role and/or password)."""

    if payload.role is not None:
        user.role = payload.role
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user: User) -> None:
    """Delete a management user."""

    await session.delete(user)
    await session.commit()
