from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.event.model import Event


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def getById(self, event_id: UUID) -> Event | None:
        return await self._session.get(Event, event_id)

    async def listPaged(self, *, page: int, size: int) -> tuple[list[Event], int]:
        total = (
            await self._session.execute(select(func.count()).select_from(Event))
        ).scalar_one()
        items_stmt = (
            select(Event)
            .order_by(Event.created_at.desc(), Event.event_id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = list((await self._session.execute(items_stmt)).scalars().all())
        return items, total

    async def create(self, event: Event) -> Event:
        self._session.add(event)
        await self._session.flush()
        return event

    async def delete(self, event: Event) -> None:
        await self._session.delete(event)
        await self._session.flush()
