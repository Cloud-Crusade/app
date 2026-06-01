import os

# 테스트는 임의 환경변수로 settings 로드 (실제 DB 미사용)
os.environ.setdefault("CORE_WRITER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("CORE_READER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RESERVATION_WRITER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("RESERVATION_READER_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.common.db import CoreBase
from app.common.deps import (
    getCoreReaderSession,
    getCoreWriterSession,
    getRedisClient,
    getReservationReaderSession,
    getReservationWriterSession,
)
from app.main import app


@pytest_asyncio.fixture
async def coreEngine():
    # StaticPool + 단일 SQLite in-memory connection 으로 매 세션이 동일 DB 를 본다
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
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


@pytest_asyncio.fixture
async def client(coreSessionFactory, redis) -> AsyncIterator[AsyncClient]:
    # 운영과 동일하게 요청마다 새 세션을 yield — autobegin/명시 begin 충돌 회피
    async def _core() -> AsyncIterator[AsyncSession]:
        async with coreSessionFactory() as session:
            yield session

    async def _redis():
        return redis

    app.dependency_overrides[getCoreWriterSession] = _core
    app.dependency_overrides[getCoreReaderSession] = _core
    app.dependency_overrides[getReservationWriterSession] = _core
    app.dependency_overrides[getReservationReaderSession] = _core
    app.dependency_overrides[getRedisClient] = _redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
