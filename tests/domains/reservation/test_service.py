from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.common.errors import (
    EventNotFoundError,
    ReservationNotFoundError,
    SeatAlreadyTakenError,
)
from app.domains.event.model import Event
from app.domains.reservation.schema import ReservationCreate
from app.domains.reservation.service import (
    ReservationReadService,
    ReservationWriteService,
    _holdKey,
)


async def _seedEvent(session) -> Event:
    start = datetime(2026, 12, 1, 19, 0, tzinfo=UTC)
    event = Event(
        user_id=uuid4(),
        title="공연",
        body=None,
        schedule={
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(hours=2)).isoformat(),
        },
        img_urls=[],
    )
    session.add(event)
    await session.flush()
    return event


@pytest.mark.asyncio
async def test_request_create_publishes_to_sqs_when_seat_free(coreSession, redis):
    event = await _seedEvent(coreSession)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="msg-1")
    user_id = uuid4()

    service = ReservationWriteService(
        core_reader_session=coreSession,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    reservation_id = await service.requestCreate(
        user_id=user_id,
        payload=ReservationCreate(event_id=event.event_id, reserved_num=7),
    )

    assert reservation_id
    sqs.publish.assert_awaited_once()
    kwargs = sqs.publish.await_args.kwargs
    assert kwargs["group_id"] == str(event.event_id)   # 같은 이벤트끼리 group
    assert kwargs["dedup_id"] == str(reservation_id)
    message = kwargs["message"]
    assert message["action"] == "reservation.create"
    assert message["reservation_id"] == str(reservation_id)
    assert message["reserved_num"] == 7
    assert await redis.get(_holdKey(event.event_id, 7)) == str(user_id)


@pytest.mark.asyncio
async def test_request_create_when_event_missing_raises(coreSession, redis):
    sqs = AsyncMock()
    service = ReservationWriteService(
        core_reader_session=coreSession,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    with pytest.raises(EventNotFoundError):
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=uuid4(), reserved_num=1),
        )
    sqs.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_create_when_seat_already_held_raises(coreSession, redis):
    event = await _seedEvent(coreSession)
    sqs = AsyncMock()
    service = ReservationWriteService(
        core_reader_session=coreSession,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    await service.requestCreate(
        user_id=uuid4(),
        payload=ReservationCreate(event_id=event.event_id, reserved_num=5),
    )
    sqs.publish.reset_mock()

    with pytest.raises(SeatAlreadyTakenError) as exc:
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event.event_id, reserved_num=5),
        )
    assert exc.value.details["reserved_num"] == 5
    sqs.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_create_releases_hold_when_sqs_publish_fails(coreSession, redis):
    event = await _seedEvent(coreSession)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(side_effect=RuntimeError("sqs down"))
    service = ReservationWriteService(
        core_reader_session=coreSession,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    with pytest.raises(RuntimeError):
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event.event_id, reserved_num=3),
        )

    # SQS 실패 시 hold 가 해제되어야 다음 요청이 가능
    assert await redis.get(_holdKey(event.event_id, 3)) is None


@pytest.mark.asyncio
async def test_get_by_id_missing_raises(coreSession):
    service = ReservationReadService(coreSession)

    with pytest.raises(ReservationNotFoundError):
        await service.getById(uuid4())


@pytest.mark.asyncio
async def test_request_cancel_publishes_with_group_id(coreSession, redis):
    from uuid import uuid4

    from app.domains.reservation.model import Reservation

    user_id = uuid4()
    reservation = Reservation(
        reservation_id=uuid4(), user_id=user_id, event_id=uuid4(), reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="msg-c")
    service = ReservationWriteService(
        core_reader_session=coreSession,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    await service.requestCancel(user_id=user_id, reservation_id=reservation.reservation_id)

    sqs.publish.assert_awaited_once()
    kwargs = sqs.publish.await_args.kwargs
    assert kwargs["group_id"] == str(reservation.event_id)   # 같은 이벤트끼리 group
    assert kwargs["dedup_id"] == f"cancel:{reservation.reservation_id}"
    message = kwargs["message"]
    assert message["action"] == "reservation.cancel"
    assert message["event_id"] == str(reservation.event_id)   # Lambda 가 cross-DB 없이 알 수 있도록
