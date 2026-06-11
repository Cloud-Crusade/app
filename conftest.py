import os

# 테스트는 임의 환경변수로 settings 로드 (실제 DB 미사용)
os.environ.setdefault("CORE_WRITER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CORE_READER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RESERVATION_WRITER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RESERVATION_READER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)
os.environ.setdefault("SQS_RESERVATION_QUEUE_URL", "http://test/reservation-queue")
# 로컬 .env 와 무관하게 테스트는 캡차 비활성 고정(결정성). 캡차 테스트는 monkeypatch 로 켠다
os.environ.setdefault("CAPTCHA_ENABLED", "false")

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from common.db import CoreBase, ReservationBase
from common.deps import (
    getCoreReaderSession,
    getCoreWriterSession,
    getRedisClient,
    getReservationReaderSession,
    getReservationSqs,
    getReservationWriterSession,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def coreEngine():
    # StaticPool + 단일 SQLite in-memory connection 으로 매 세션이 동일 DB 를 본다.
    # create_all 은 테스트가 import 한 서비스 모델만 생성한다(서비스별로 다름).
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(ReservationBase.metadata.create_all)
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
async def client(app, coreSessionFactory, redis, sqsMock) -> AsyncIterator[AsyncClient]:
    # app 은 각 서비스의 tests/conftest.py 가 제공 (해당 서비스 FastAPI 앱)
    async def _core() -> AsyncIterator[AsyncSession]:
        async with coreSessionFactory() as session:
            yield session

    async def _redis():
        return redis

    def _sqs():
        return sqsMock

    app.dependency_overrides[getCoreWriterSession] = _core
    app.dependency_overrides[getCoreReaderSession] = _core
    app.dependency_overrides[getReservationWriterSession] = _core
    app.dependency_overrides[getReservationReaderSession] = _core
    app.dependency_overrides[getRedisClient] = _redis
    app.dependency_overrides[getReservationSqs] = _sqs

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
