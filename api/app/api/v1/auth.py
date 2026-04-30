from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import Settings
from api.app.deps import get_current_user, get_db_session
from api.app.schemas.auth import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    CurrentUser,
    LoginRequest,
    TokenResponse,
)
from api.app.services.auth_service import (
    AuthenticationError,
    authenticate_user,
    create_api_key,
    issue_user_token,
    list_api_keys,
    revoke_api_key,
)

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: DbSession,
) -> TokenResponse:
    """Authenticate a management user and return a bearer JWT."""

    try:
        user = await authenticate_user(session, payload.email, payload.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    settings: Settings = request.app.state.settings
    return TokenResponse(
        access_token=issue_user_token(settings, user),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        request_id=request.state.request_id,
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key_endpoint(
    payload: ApiKeyCreateRequest,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> ApiKeyCreateResponse:
    """Create an API key for the current tenant and return the plaintext key once."""

    settings: Settings = request.app.state.settings
    api_key, plaintext_key = await create_api_key(session, settings, current_user, payload)
    return ApiKeyCreateResponse(
        **ApiKeyResponse.model_validate(api_key).model_dump(),
        api_key=plaintext_key,
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys_endpoint(
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> ApiKeyListResponse:
    """List API keys belonging to the current tenant."""

    api_keys = await list_api_keys(session, current_user.tenant_id)
    return ApiKeyListResponse(
        request_id=request.state.request_id,
        data=[ApiKeyResponse.model_validate(api_key) for api_key in api_keys],
    )


@router.delete("/api-keys/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key_endpoint(
    api_key_id: UUID,
    current_user: CurrentUserDep,
    session: DbSession,
) -> Response:
    """Revoke an API key owned by the current tenant."""

    revoked = await revoke_api_key(session, current_user.tenant_id, api_key_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
