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

    async def allow_sliding_window(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now_ms: int,
        member: str,
    ) -> tuple[bool, int]:
        """Apply a Redis sorted-set sliding window rate-limit check."""

        window_start_ms = now_ms - (window_seconds * 1000)
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start_ms)
        pipe.zcard(key)
        results = await pipe.execute()
        current_count = int(results[1])
        if current_count >= limit:
            oldest = await self._client.zrange(key, 0, 0, withscores=True)
            if not oldest:
                return False, 1
            retry_after_ms = int(oldest[0][1]) + (window_seconds * 1000) - now_ms
            return False, max(1, (retry_after_ms + 999) // 1000)

        await self._client.zadd(key, {member: now_ms})
        await self._client.expire(key, window_seconds)
        return True, 0

    async def close(self) -> None:
        """Close the Redis connection pool."""

        await self._client.aclose()
