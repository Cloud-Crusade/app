from typing import Annotated

from common.deps import getCoreReaderSession
from common.errors import UserNotFoundError
from common.security import decodeToken
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.user.model import User
from app.domains.user.repository import UserRepository

bearerScheme = HTTPBearer(
    bearerFormat="JWT",
    description="`POST /auth/login` 으로 발급받은 access token 을 입력합니다.",
)


async def getCurrentUser(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearerScheme)],
    session: Annotated[AsyncSession, Depends(getCoreReaderSession)],
) -> User:
    payload = decodeToken(credentials.credentials, expected_type="access")
    user: User | None = await UserRepository(session).getById(payload.user_id)
    if user is None:
        raise UserNotFoundError(user_id=str(payload.user_id))
    return user
