from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Stable error payload returned by public API endpoints."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(examples=["RESOURCE_NOT_FOUND"])
    message: str = Field(examples=["Knowledge base not found"])
    detail: dict[str, Any] | None = None
    request_id: str
    type: str = Field(examples=["https://docs.byob.dev/errors/RESOURCE_NOT_FOUND"])


class ErrorResponse(BaseModel):
    """RFC 7807-inspired error response wrapper used by the platform."""

    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


class Pagination(BaseModel):
    """Cursor pagination metadata for list endpoints."""

    model_config = ConfigDict(extra="forbid")

    cursor: str | None = None
    has_more: bool
    total: int | None = None
