from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.user.model import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def getById(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def getByName(self, user_name: str) -> User | None:
        stmt = select(User).where(User.user_name == user_name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user
