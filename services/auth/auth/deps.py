from typing import Annotated

from common.auth import bearerScheme, unauthenticated
from common.errors import UserNotFoundError
from common.security import decodeToken
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db import getReaderSession
from auth.domains.user.model import User
from auth.domains.user.repository import UserRepository


async def getCurrentUser(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearerScheme)],
    session: Annotated[AsyncSession, Depends(getReaderSession)],
) -> User:
    # auth 서비스만 User 테이블을 소유 — 전체 User 로드 (프로필 응답용)
    if credentials is None:
        raise unauthenticated()
    payload = decodeToken(credentials.credentials, expected_type="access")
    user: User | None = await UserRepository(session).getById(payload.user_id)
    if user is None:
        raise UserNotFoundError(user_id=str(payload.user_id))
    return user
