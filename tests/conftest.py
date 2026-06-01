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
async def coreSession() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def redis() -> AsyncIterator:
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client(coreSession, redis) -> AsyncIterator[AsyncClient]:
    async def _core():
        yield coreSession

    async def _redis():
        return redis

    async def _stub_session():
        yield coreSession  # reservation 도 같은 세션으로 stub (인증 도메인 테스트에선 미사용)

    app.dependency_overrides[getCoreWriterSession] = _core
    app.dependency_overrides[getCoreReaderSession] = _core
    app.dependency_overrides[getReservationWriterSession] = _stub_session
    app.dependency_overrides[getReservationReaderSession] = _stub_session
    app.dependency_overrides[getRedisClient] = _redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
