from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.deps import get_db_session, require_admin
from api.app.schemas.auth import CurrentUser
from api.app.schemas.user import (
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserResponseEnvelope,
    UserUpdateRequest,
)
from api.app.services.user_service import (
    UserAlreadyExistsError,
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]


@router.get("", response_model=UserListResponse)
async def list_users_endpoint(
    request: Request,
    admin: AdminDep,
    session: DbSession,
) -> UserListResponse:
    """List management console users."""

    users = await list_users(session)
    return UserListResponse(
        request_id=request.state.request_id,
        data=[UserResponse.model_validate(user) for user in users],
    )


@router.post("", response_model=UserResponseEnvelope, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    payload: UserCreateRequest,
    request: Request,
    admin: AdminDep,
    session: DbSession,
) -> UserResponseEnvelope:
    """Create a management user with the provided role and password."""

    try:
        user = await create_user(session, payload)
    except UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        ) from exc
    return UserResponseEnvelope(
        request_id=request.state.request_id,
        data=UserResponse.model_validate(user),
    )


@router.patch("/{user_id}", response_model=UserResponseEnvelope)
async def update_user_endpoint(
    user_id: UUID,
    payload: UserUpdateRequest,
    request: Request,
    admin: AdminDep,
    session: DbSession,
) -> UserResponseEnvelope:
    """Update a management user's role or password."""

    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    updated = await update_user(session, user, payload)
    return UserResponseEnvelope(
        request_id=request.state.request_id,
        data=UserResponse.model_validate(updated),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: UUID,
    admin: AdminDep,
    session: DbSession,
) -> Response:
    """Delete a management user. Administrators cannot delete themselves."""

    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot delete their own account",
        )
    user = await get_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await delete_user(session, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
