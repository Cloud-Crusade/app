from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.common.errors import EventNotFoundError
from app.domains.event.schema import EventCreate, EventUpdate, Schedule
from app.domains.event.service import EventService


def _payload(*, title: str = "공연 A") -> EventCreate:
    start = datetime(2026, 12, 1, 19, 0, tzinfo=UTC)
    return EventCreate(
        title=title,
        body="설명",
        schedule=Schedule(start_at=start, end_at=start + timedelta(hours=2)),
        img_urls=["https://cdn.example.com/a.jpg"],
    )


@pytest.mark.asyncio
async def test_create_event_persists_owner_and_payload(coreSession):
    service = EventService(coreSession)
    user_id = uuid4()

    event = await service.create(user_id=user_id, payload=_payload())

    assert event.event_id
    assert event.user_id == user_id
    assert event.title == "공연 A"
    assert event.schedule["start_at"].startswith("2026-12-01")
    assert event.img_urls == ["https://cdn.example.com/a.jpg"]


@pytest.mark.asyncio
async def test_get_by_id_when_missing_raises(coreSession):
    service = EventService(coreSession)

    with pytest.raises(EventNotFoundError):
        await service.getById(uuid4())


@pytest.mark.asyncio
async def test_list_paged_orders_newest_first(coreSession):
    service = EventService(coreSession)
    user_id = uuid4()
    for title in ("A", "B", "C"):
        await service.create(user_id=user_id, payload=_payload(title=title))

    items, total = await service.listPaged(page=1, size=10)

    assert total == 3
    assert {e.title for e in items} == {"A", "B", "C"}


@pytest.mark.asyncio
async def test_update_partial_fields(coreSession):
    service = EventService(coreSession)
    user_id = uuid4()
    event = await service.create(user_id=user_id, payload=_payload())

    updated = await service.update(
        event_id=event.event_id,
        payload=EventUpdate(title="공연 변경"),
    )

    assert updated.title == "공연 변경"
    assert updated.body == "설명"


@pytest.mark.asyncio
async def test_update_missing_raises(coreSession):
    service = EventService(coreSession)

    with pytest.raises(EventNotFoundError):
        await service.update(event_id=uuid4(), payload=EventUpdate(title="x"))


@pytest.mark.asyncio
async def test_delete_event(coreSession):
    service = EventService(coreSession)
    user_id = uuid4()
    event = await service.create(user_id=user_id, payload=_payload())

    await service.delete(event_id=event.event_id)

    with pytest.raises(EventNotFoundError):
        await service.getById(event.event_id)


@pytest.mark.asyncio
async def test_delete_missing_raises(coreSession):
    service = EventService(coreSession)

    with pytest.raises(EventNotFoundError):
        await service.delete(event_id=uuid4())


def test_schedule_rejects_inverted_order():
    start = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    with pytest.raises(ValueError):
        Schedule(start_at=start, end_at=start - timedelta(hours=1))
