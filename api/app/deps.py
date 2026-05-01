from collections.abc import AsyncIterator
from uuid import UUID

import jwt
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.app.config import Settings
from api.app.core.security import decode_access_token
from api.app.models.user import User
from api.app.schemas.auth import CurrentUser


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield an async database session from the application session factory."""

    session_factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session


async def get_current_user(request: Request) -> CurrentUser:
    """Return the management user represented by a bearer JWT."""

    authorization = request.headers.get("Authorization")
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.removeprefix("Bearer ").strip()
    return await get_current_user_from_token(request, token)


async def get_current_user_or_query_token(request: Request) -> CurrentUser:
    """Return the current user from a bearer token or asset access query token."""

    authorization = request.headers.get("Authorization")
    if authorization is not None and authorization.startswith("Bearer "):
        return await get_current_user_from_token(
            request,
            authorization.removeprefix("Bearer ").strip(),
        )

    token = request.query_params.get("access_token")
    if token:
        return await get_current_user_from_token(request, token)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_from_token(request: Request, token: str) -> CurrentUser:
    """Resolve a management user from an access token string."""

    settings: Settings = request.app.state.settings
    try:
        payload = decode_access_token(settings, token)
        user_id = UUID(str(payload["sub"]))
        email = str(payload["email"])
        _role_claim = str(payload["role"])
    except (KeyError, ValueError, jwt.PyJWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    session_factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with session_factory() as session:
        user = await session.scalar(
            select(User).where(
                User.id == user_id,
                User.email == email,
            )
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user_id = user_id
    request.state.user_role = user.role
    return CurrentUser(id=user.id, email=user.email, role=user.role)


async def require_admin(request: Request) -> CurrentUser:
    """Authenticate the current user and require an admin role."""

    current_user = await get_current_user(request)
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user
