from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ComponentStatus = Literal["ok", "degraded", "down"]


class HealthCheck(BaseModel):
    """Health state for one platform dependency or subsystem."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: ComponentStatus
    latency_ms: float | None = Field(default=None, ge=0)


class HealthResponse(BaseModel):
    """Public health check response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: ComponentStatus
    service: str
    environment: str
    version: str
    checks: list[HealthCheck]
