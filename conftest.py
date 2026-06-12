import os

# 테스트는 임의 환경변수로 settings 로드 (실제 DB 미사용)
os.environ.setdefault("DB_WRITER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DB_READER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)
os.environ.setdefault("SQS_RESERVATION_QUEUE_URL", "http://test/reservation-queue")
# 로컬 .env 와 무관하게 테스트는 캡차 비활성 고정(결정성). 캡차 테스트는 monkeypatch 로 켠다
os.environ.setdefault("CAPTCHA_ENABLED", "false")

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from common.deps import getRedisClient, getReservationSqs
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


# serviceBase·sessionDeps 는 각 서비스의 tests/conftest.py 가 제공(override).
@pytest.fixture
def serviceBase():
    raise RuntimeError("각 서비스 conftest 가 serviceBase 를 제공해야 합니다")


@pytest.fixture
def sessionDeps():
    # (getReaderSession, getWriterSession) — 해당 서비스 db 의 세션 의존성
    raise RuntimeError("각 서비스 conftest 가 sessionDeps 를 제공해야 합니다")


@pytest_asyncio.fixture
async def coreEngine(serviceBase):
    # StaticPool + 단일 SQLite in-memory connection 으로 매 세션이 동일 DB 를 본다.
    # 해당 서비스의 Base 테이블만 생성한다(서비스별 소유).
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(serviceBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def coreSessionFactory(coreEngine):
    return async_sessionmaker(coreEngine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def coreSession(coreSessionFactory) -> AsyncIterator[AsyncSession]:
    async with coreSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def redis() -> AsyncIterator:
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def sqsMock() -> AsyncMock:
    publisher = AsyncMock()
    publisher.publish = AsyncMock(return_value="msg-id-test")
    return publisher


@pytest_asyncio.fixture
async def client(
    app, coreSessionFactory, redis, sqsMock, sessionDeps,
) -> AsyncIterator[AsyncClient]:
    async def _session() -> AsyncIterator[AsyncSession]:
        async with coreSessionFactory() as session:
            yield session

    async def _redis():
        return redis

    def _sqs():
        return sqsMock

    reader_dep, writer_dep = sessionDeps
    app.dependency_overrides[reader_dep] = _session
    app.dependency_overrides[writer_dep] = _session
    app.dependency_overrides[getRedisClient] = _redis
    app.dependency_overrides[getReservationSqs] = _sqs

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
