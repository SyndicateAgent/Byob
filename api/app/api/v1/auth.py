from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import Settings
from api.app.deps import get_db_session
from api.app.schemas.auth import (
    LoginRequest,
    TokenResponse,
)
from api.app.services.auth_service import (
    AuthenticationError,
    authenticate_user,
    issue_user_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


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
