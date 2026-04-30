from time import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from starlette.types import ASGIApp

from api.app.core.redis_client import RedisClient

RATE_LIMIT_WINDOW_SECONDS = 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforce per-API-key sliding-window limits with Redis."""

    def __init__(self, app: ASGIApp, window_seconds: int = RATE_LIMIT_WINDOW_SECONDS) -> None:
        super().__init__(app)
        self._window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Apply rate limiting only after API key context has been injected."""

        api_key_id = getattr(request.state, "api_key_id", None)
        rate_limit = getattr(request.state, "api_key_rate_limit", None)
        if api_key_id is None or rate_limit is None:
            return await call_next(request)

        redis_client: RedisClient = request.app.state.redis_client
        request_id = getattr(request.state, "request_id", "")
        now_ms = int(time() * 1000)
        allowed, retry_after = await redis_client.allow_sliding_window(
            f"rate_limit:api_key:{api_key_id}",
            limit=int(rate_limit),
            window_seconds=self._window_seconds,
            now_ms=now_ms,
            member=f"{request_id}:{now_ms}",
        )
        if allowed:
            return await call_next(request)

        return JSONResponse(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "API key rate limit exceeded",
                    "detail": {"retry_after": retry_after},
                    "request_id": request_id,
                    "type": "https://docs.kb-platform.com/errors/RATE_LIMITED",
                }
            },
            headers={"Retry-After": str(retry_after)},
        )
