from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to logs, request state, and response headers."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._logger = structlog.get_logger(__name__)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Populate request-scoped context before dispatching to route handlers."""

        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
