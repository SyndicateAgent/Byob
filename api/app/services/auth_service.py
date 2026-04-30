from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import Settings
from api.app.core.security import (
    create_access_token,
    generate_api_key,
    hash_api_key,
    validate_api_key_format,
    verify_password,
)
from api.app.models.api_key import ApiKey
from api.app.models.user import User
from api.app.schemas.auth import ApiKeyCreateRequest, CurrentUser


class AuthenticationError(Exception):
    """Raised when supplied credentials are invalid."""


class ApiKeyAuthenticationError(Exception):
    """Raised when an API key cannot authenticate a request."""


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
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )


async def create_api_key(
    session: AsyncSession,
    settings: Settings,
    current_user: CurrentUser,
    payload: ApiKeyCreateRequest,
) -> tuple[ApiKey, str]:
    """Create an API key for the current user's tenant and return it once."""

    plaintext_key = generate_api_key(payload.environment)
    api_key = ApiKey(
        tenant_id=current_user.tenant_id,
        name=payload.name,
        key_hash=hash_api_key(plaintext_key),
        key_prefix=plaintext_key[:17],
        scopes=payload.scopes,
        rate_limit=payload.rate_limit or settings.default_api_key_rate_limit,
        expires_at=payload.expires_at,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return api_key, plaintext_key


async def list_api_keys(session: AsyncSession, tenant_id: UUID) -> list[ApiKey]:
    """Return API keys belonging to one tenant."""

    result = await session.execute(
        select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_api_key(session: AsyncSession, tenant_id: UUID, api_key_id: UUID) -> bool:
    """Mark an API key as revoked if it belongs to the tenant."""

    result = await session.execute(
        select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.tenant_id == tenant_id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return False

    api_key.revoked = True
    await session.commit()
    return True


async def authenticate_api_key(session: AsyncSession, plaintext_key: str) -> ApiKey:
    """Validate an external API key and return its stored record."""

    if not validate_api_key_format(plaintext_key):
        raise ApiKeyAuthenticationError("Invalid API key format")

    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(plaintext_key))
    )
    api_key = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if api_key is None or api_key.revoked:
        raise ApiKeyAuthenticationError("Invalid API key")
    if api_key.expires_at is not None and api_key.expires_at <= now:
        raise ApiKeyAuthenticationError("API key expired")

    api_key.last_used_at = now
    await session.commit()
    await session.refresh(api_key)
    return api_key
