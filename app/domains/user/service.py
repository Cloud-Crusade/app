from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import (
    DuplicateUserNameError,
    InvalidCredentialsError,
)
from app.common.security import hashPassword, verifyPassword
from app.domains.user.model import User
from app.domains.user.repository import UserRepository
from app.domains.user.schema import SignupRequest


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def signup(self, payload: SignupRequest) -> User:
        user = User(
            user_name=payload.user_name,
            password_hash=hashPassword(payload.password),
        )
        try:
            async with self._session.begin():
                return await self._users.create(user)
        except IntegrityError as exc:
            raise DuplicateUserNameError(user_name=payload.user_name) from exc

    async def authenticate(self, *, user_name: str, password: str) -> User:
        user = await self._users.getByName(user_name)
        if user is None or not verifyPassword(password, user.password_hash):
            raise InvalidCredentialsError()
        return user
