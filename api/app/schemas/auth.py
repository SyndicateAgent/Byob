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
    email: EmailStr
    role: str
