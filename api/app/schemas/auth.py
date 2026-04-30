from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    """Credentials for management console login."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """JWT response for authenticated management users."""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    request_id: str


class CurrentUser(BaseModel):
    """Authenticated management user context."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: str


class ApiKeyCreateRequest(BaseModel):
    """Input for creating an API key."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    rate_limit: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    environment: str = Field(default="live", pattern="^(live|test)$")


class ApiKeyResponse(BaseModel):
    """API key metadata returned by management endpoints."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    name: str
    key_prefix: str | None
    scopes: list[object]
    rate_limit: int
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked: bool
    created_at: datetime


class ApiKeyCreateResponse(ApiKeyResponse):
    """API key creation response containing the plaintext key once."""

    api_key: str


class ApiKeyListResponse(BaseModel):
    """List response for API key metadata."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[ApiKeyResponse]


class UsageDailyResponse(BaseModel):
    """Daily usage aggregate exposed to management users."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    date: date
    api_calls: int
    retrieval_calls: int
    documents_uploaded: int
    chunks_created: int
    embedding_tokens: int
    storage_bytes: int


class UsageResponse(BaseModel):
    """Tenant usage response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    tenant_id: UUID
    data: list[UsageDailyResponse]
