from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import (
    coreReaderFactory,
    coreWriterFactory,
    reservationReaderFactory,
    reservationWriterFactory,
)
from app.common.errors import InvalidTokenError, UserNotFoundError
from app.common.redis import buildRedis
from app.common.security import decodeToken


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


async def getCurrentUser(
    authorization: Annotated[str, Header()],
    session: Annotated[AsyncSession, Depends(getCoreReaderSession)],
):
    # 지연 import — domains/user 가 common 을 import 하지 않도록 의존 방향 유지
    from app.domains.user.model import User
    from app.domains.user.repository import UserRepository

    if not authorization.startswith("Bearer "):
        raise InvalidTokenError()
    token = authorization.removeprefix("Bearer ")
    payload = decodeToken(token, expected_type="access")
    user: User | None = await UserRepository(session).getById(payload.user_id)
    if user is None:
        raise UserNotFoundError(user_id=str(payload.user_id))
    return user
