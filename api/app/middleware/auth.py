from collections.abc import Sequence
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.types import ASGIApp

from api.app.models.api_key import ApiKey
from api.app.services.auth_service import ApiKeyAuthenticationError, authenticate_api_key

API_KEY_HEADER = "X-API-Key"
API_KEY_PROTECTED_PREFIXES = ("/api/v1/retrieval", "/api/v1/chunks")


def path_requires_api_key(path: str, protected_prefixes: Sequence[str]) -> bool:
    """Return whether the request path is part of the external API surface."""

    return any(path.startswith(prefix) for prefix in protected_prefixes)


def extract_api_key(request: Request) -> str | None:
    """Extract an API key from supported request headers."""

    header_value = request.headers.get(API_KEY_HEADER)
    if header_value:
        return header_value.strip()

    authorization = request.headers.get("Authorization")
    if authorization is not None and authorization.startswith("Bearer kb_"):
        return authorization.removeprefix("Bearer ").strip()
    return None


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Authenticate external API requests with tenant-scoped API keys."""

    def __init__(
        self,
        app: ASGIApp,
        protected_prefixes: Sequence[str] = API_KEY_PROTECTED_PREFIXES,
    ) -> None:
        super().__init__(app)
        self._protected_prefixes = protected_prefixes
        self._logger = structlog.get_logger(__name__)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Authenticate API-key protected routes before route handlers run."""

        if not path_requires_api_key(request.url.path, self._protected_prefixes):
            return await call_next(request)

        plaintext_key = extract_api_key(request)
        if plaintext_key is None:
            return self._unauthorized(request, "Missing API key")

        session_factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
        async with session_factory() as session:
            try:
                api_key = await authenticate_api_key(session, plaintext_key)
            except ApiKeyAuthenticationError:
                self._logger.warning("api_key_authentication_failed")
                return self._unauthorized(request, "Invalid API key")

        bind_api_key_context(request, api_key)
        return await call_next(request)

    def _unauthorized(self, request: Request, message: str) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "")
        return JSONResponse(
            status_code=HTTP_401_UNAUTHORIZED,
            content={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": message,
                    "detail": None,
                    "request_id": request_id,
                    "type": "https://docs.kb-platform.com/errors/UNAUTHORIZED",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )


def bind_api_key_context(request: Request, api_key: ApiKey) -> None:
    """Attach authenticated API key and tenant context to request state."""

    request.state.tenant_id = api_key.tenant_id
    request.state.api_key_id = api_key.id
    request.state.api_key_scopes = api_key.scopes
    request.state.api_key_rate_limit = api_key.rate_limit
    structlog.contextvars.bind_contextvars(
        tenant_id=str(UUID(str(api_key.tenant_id))),
        api_key_id=str(UUID(str(api_key.id))),
    )
