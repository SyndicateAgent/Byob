from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserResponse(BaseModel):
    """User metadata returned to administrators."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    email: str
    role: str
    created_at: datetime


class UserCreateRequest(BaseModel):
    """Input for creating a management user."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    role: str = Field(default="viewer", pattern="^(admin|editor|viewer)$")


class UserUpdateRequest(BaseModel):
    """Mutable user fields available to administrators."""

    model_config = ConfigDict(extra="forbid")

    role: str | None = Field(default=None, pattern="^(admin|editor|viewer)$")
    password: str | None = Field(default=None, min_length=12, max_length=128)


class UserListResponse(BaseModel):
    """List response for management users."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[UserResponse]


class UserResponseEnvelope(BaseModel):
    """Single user response envelope including request id."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: UserResponse
