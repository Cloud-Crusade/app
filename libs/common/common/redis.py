from redis.asyncio import ConnectionPool, Redis

from common.settings import settings

_pool: ConnectionPool | None = None


def buildRedis() -> Redis:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url, max_connections=50, decode_responses=True,
        )
    return Redis(connection_pool=_pool)
