from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import EventNotFoundError
from app.domains.event.model import Event
from app.domains.event.repository import EventRepository
from app.domains.event.schema import EventCreate, EventUpdate

MAX_PAGE_SIZE = 100


class EventService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._events = EventRepository(session)

    async def getById(self, event_id: UUID) -> Event:
        event = await self._events.getById(event_id)
        if event is None:
            raise EventNotFoundError(event_id=str(event_id))
        return event

    async def listPaged(self, *, page: int, size: int) -> tuple[list[Event], int]:
        page = max(page, 1)
        size = max(1, min(size, MAX_PAGE_SIZE))
        return await self._events.listPaged(page=page, size=size)

    async def create(self, *, user_id: UUID, payload: EventCreate) -> Event:
        event = Event(
            user_id=user_id,
            title=payload.title,
            body=payload.body,
            schedule=payload.schedule.model_dump(mode="json"),
            img_urls=payload.img_urls,
        )
        async with self._session.begin():
            return await self._events.create(event)

    async def update(self, *, event_id: UUID, payload: EventUpdate) -> Event:
        async with self._session.begin():
            event = await self._events.getById(event_id)
            if event is None:
                raise EventNotFoundError(event_id=str(event_id))
            if payload.title is not None:
                event.title = payload.title
            if payload.body is not None:
                event.body = payload.body
            if payload.schedule is not None:
                event.schedule = payload.schedule.model_dump(mode="json")
            if payload.img_urls is not None:
                event.img_urls = payload.img_urls
            return event

    async def delete(self, *, event_id: UUID) -> None:
        async with self._session.begin():
            event = await self._events.getById(event_id)
            if event is None:
                raise EventNotFoundError(event_id=str(event_id))
            await self._events.delete(event)
