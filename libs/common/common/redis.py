from config.settings import settings
from redis.asyncio import ConnectionPool, Redis

_pool: ConnectionPool | None = None


def buildRedis() -> Redis:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=50,
            decode_responses=True,
            # idle 커넥션 주기 검증 → 페일오버·컷오버 시 새 커넥션이 DNS 재해석으로 재연결
            health_check_interval=settings.redis_health_check_interval_seconds,
            socket_keepalive=True,
        )
    return Redis(connection_pool=_pool)
