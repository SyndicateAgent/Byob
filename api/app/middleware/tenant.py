from uuid import UUID

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Bind authenticated tenant context for downstream handlers and logs."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Propagate tenant context only from authenticated middleware/dependencies."""

        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is not None:
            structlog.contextvars.bind_contextvars(tenant_id=str(UUID(str(tenant_id))))

        response = await call_next(request)
        if tenant_id is not None:
            response.headers["X-Tenant-ID"] = str(UUID(str(tenant_id)))
        return response
