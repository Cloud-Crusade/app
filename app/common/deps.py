from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import (
    coreReaderFactory,
    coreWriterFactory,
    reservationReaderFactory,
    reservationWriterFactory,
)
from app.common.errors import UserNotFoundError
from app.common.redis import buildRedis
from app.common.security import decodeToken
from app.common.sqs import SqsPublisher, getReservationSqsPublisher

bearerScheme = HTTPBearer(
    bearerFormat="JWT",
    description="`POST /auth/login` 으로 발급받은 access token 을 입력합니다.",
)


async def getCoreWriterSession() -> AsyncIterator[AsyncSession]:
    async with coreWriterFactory() as session:
        yield session


async def getCoreReaderSession() -> AsyncIterator[AsyncSession]:
    async with coreReaderFactory() as session:
        yield session


async def getReservationWriterSession() -> AsyncIterator[AsyncSession]:
    async with reservationWriterFactory() as session:
        yield session


async def getReservationReaderSession() -> AsyncIterator[AsyncSession]:
    async with reservationReaderFactory() as session:
        yield session


def getRedisClient() -> Redis:
    return buildRedis()


def getReservationSqs() -> SqsPublisher:
    return getReservationSqsPublisher()


async def getCurrentUser(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearerScheme)],
    session: Annotated[AsyncSession, Depends(getCoreReaderSession)],
):
    # 지연 import — domains/user 가 common 을 import 하지 않도록 의존 방향 유지
    from app.domains.user.model import User
    from app.domains.user.repository import UserRepository

    payload = decodeToken(credentials.credentials, expected_type="access")
    user: User | None = await UserRepository(session).getById(payload.user_id)
    if user is None:
        raise UserNotFoundError(user_id=str(payload.user_id))
    return user
