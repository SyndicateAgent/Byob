from redis.asyncio import Redis


class RedisClient:
    """Async Redis client wrapper used for cache, queues, and health checks."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self._client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )

    async def ping(self) -> None:
        """Verify Redis accepts commands."""

        response = await self._client.ping()
        if response is not True:
            raise RuntimeError("Redis ping failed")

    async def close(self) -> None:
        """Close the Redis connection pool."""

        await self._client.aclose()
