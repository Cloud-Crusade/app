from datetime import date
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common.errors import (
    EventNotFoundError,
    EventSoldOutError,
    ReservationNotFoundError,
    SeatAlreadyTakenError,
    SeatOutOfRangeError,
)
from reservation.domains.reservation.schema import ReservationCreate, ReservationRead
from reservation.domains.reservation.service import (
    ReservationReadService,
    ReservationWriteService,
    _holdKey,
    _remainKey,
    _reservationCacheKey,
)


class FakeEventClient:
    def __init__(self, total_seats: int | None = 100) -> None:
        self._total_seats = total_seats

    async def getTotalSeats(self, event_id: UUID) -> int | None:
        return self._total_seats




@pytest.mark.asyncio
async def test_request_create_publishes_to_sqs_when_seat_free(coreSession, redis):
    event_id = uuid4()
    event_client = FakeEventClient()
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="msg-1")
    user_id = uuid4()

    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    reservation_id = await service.requestCreate(
        user_id=user_id,
        payload=ReservationCreate(event_id=event_id, reserved_num=7),
    )

    assert reservation_id
    sqs.publish.assert_awaited_once()
    kwargs = sqs.publish.await_args.kwargs
    assert kwargs["group_id"] == str(event_id)   # 같은 이벤트끼리 group
    assert kwargs["dedup_id"] == str(reservation_id)
    message = kwargs["message"]
    assert message["action"] == "reservation.create"
    assert message["reservation_id"] == str(reservation_id)
    assert message["reserved_num"] == 7
    assert await redis.get(_holdKey(event_id, 7)) == str(user_id)


@pytest.mark.asyncio
async def test_request_create_when_event_missing_raises(coreSession, redis):
    event_client = FakeEventClient(total_seats=None)
    sqs = AsyncMock()
    service = ReservationWriteService(
        event_client=event_client,
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
    event_id = uuid4()
    event_client = FakeEventClient()
    sqs = AsyncMock()
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    await service.requestCreate(
        user_id=uuid4(),
        payload=ReservationCreate(event_id=event_id, reserved_num=5),
    )
    sqs.publish.reset_mock()

    with pytest.raises(SeatAlreadyTakenError) as exc:
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event_id, reserved_num=5),
        )
    assert exc.value.details["reserved_num"] == 5
    sqs.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_missing_raises(coreSession):
    service = ReservationReadService(coreSession)

    with pytest.raises(ReservationNotFoundError):
        await service.getById(uuid4())


@pytest.mark.asyncio
async def test_request_create_decrements_remain_counter(coreSession, redis):
    event_id = uuid4()
    event_client = FakeEventClient(total_seats=10)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    await service.requestCreate(
        user_id=uuid4(),
        payload=ReservationCreate(event_id=event_id, reserved_num=1),
    )

    remain = int(await redis.get(_remainKey(event_id)))
    assert remain == 9  # 10 → DECR 한 번


@pytest.mark.asyncio
async def test_request_create_rejects_seat_above_total(coreSession, redis):
    event_id = uuid4()
    event_client = FakeEventClient(total_seats=5)
    sqs = AsyncMock()
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    with pytest.raises(SeatOutOfRangeError) as exc:
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event_id, reserved_num=99),
        )
    assert exc.value.details["total_seats"] == 5
    sqs.publish.assert_not_awaited()
    # 범위 위반은 카운터 DECR 전이라 잔여가 줄지 않아야 함
    assert await redis.get(_remainKey(event_id)) is None


@pytest.mark.asyncio
async def test_request_create_sold_out_when_counter_exhausted(coreSession, redis):
    event_id = uuid4()
    event_client = FakeEventClient(total_seats=2)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    # 좌석 1, 2 정상 점유
    await service.requestCreate(
        user_id=uuid4(), payload=ReservationCreate(event_id=event_id, reserved_num=1),
    )
    await service.requestCreate(
        user_id=uuid4(), payload=ReservationCreate(event_id=event_id, reserved_num=2),
    )
    sqs.publish.reset_mock()

    # 3번째 요청 — 범위는 OK 가 아니므로 SeatOutOfRange. 대신 같은 범위에서 더 시도
    # → total_seats=2 라 reserved_num 은 1 또는 2 만 가능. 카운터 매진 검증을 위해
    # 다른 좌석 번호로 시도하더라도 같은 결과 (SeatAlreadyTaken)
    # 매진 자체 검증은 hold 우회 시점만 가능하므로, 카운터 직접 0 셋팅 후 검증
    await redis.set(_remainKey(event_id), 0)

    with pytest.raises(EventSoldOutError):
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event_id, reserved_num=1),
        )
    sqs.publish.assert_not_awaited()
    # 매진 검증 후 카운터는 0 으로 복구되어야 함
    assert int(await redis.get(_remainKey(event_id))) == 0


@pytest.mark.asyncio
async def test_request_create_seat_taken_restores_counter(coreSession, redis):
    event_id = uuid4()
    event_client = FakeEventClient(total_seats=10)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    await service.requestCreate(
        user_id=uuid4(),
        payload=ReservationCreate(event_id=event_id, reserved_num=5),
    )
    remain_after_first = int(await redis.get(_remainKey(event_id)))
    assert remain_after_first == 9

    # 같은 좌석 다시 시도 → SeatAlreadyTaken. 카운터는 복구되어야 (9 유지)
    with pytest.raises(SeatAlreadyTakenError):
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event_id, reserved_num=5),
        )
    assert int(await redis.get(_remainKey(event_id))) == 9


@pytest.mark.asyncio
async def test_request_create_sqs_failure_restores_both_hold_and_counter(coreSession, redis):
    event_id = uuid4()
    event_client = FakeEventClient(total_seats=10)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(side_effect=RuntimeError("sqs down"))
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    with pytest.raises(RuntimeError):
        await service.requestCreate(
            user_id=uuid4(),
            payload=ReservationCreate(event_id=event_id, reserved_num=3),
        )

    # 양쪽 모두 보상되어야 함
    assert await redis.get(_holdKey(event_id, 3)) is None
    assert int(await redis.get(_remainKey(event_id))) == 10


@pytest.mark.asyncio
async def test_request_cancel_publishes_with_group_id(coreSession, redis):
    event_client = FakeEventClient()
    from uuid import uuid4

    from reservation.domains.reservation.model import Reservation

    user_id = uuid4()
    reservation = Reservation(
        reservation_id=uuid4(), user_id=user_id, event_id=uuid4(), reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="msg-c")
    service = ReservationWriteService(
        event_client=event_client,
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
    assert message["reserved_num"] == reservation.reserved_num   # Lambda 가 seat:hold 키 구성 가능


@pytest.mark.asyncio
async def test_request_cancel_pending_reservation_from_cache(coreSession, redis):
    event_client = FakeEventClient()
    # 미영속(DB 미반영) 예매 — 캐시에만 존재해도 취소 가능해야 함 (cache-first)
    user_id = uuid4()
    event_id = uuid4()
    rid = uuid4()
    cached = ReservationRead(
        reservation_id=rid,
        user_id=user_id,
        event_id=event_id,
        is_canceled=False,
        reserved_num=5,
        created_at=date(2026, 6, 5),
        last_modified=None,
    )
    await redis.set(_reservationCacheKey(rid), cached.model_dump_json())

    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="msg-c")
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,  # DB 에는 없음
        redis=redis,
        sqs=sqs,
    )

    await service.requestCancel(user_id=user_id, reservation_id=rid)

    sqs.publish.assert_awaited_once()
    message = sqs.publish.await_args.kwargs["message"]
    assert message["event_id"] == str(event_id)
    assert message["reserved_num"] == 5
    # 취소 즉시 단건 캐시 무효화
    assert await redis.get(_reservationCacheKey(rid)) is None


@pytest.mark.asyncio
async def test_request_cancel_already_canceled_raises_and_skips_publish(coreSession, redis):
    event_client = FakeEventClient()
    # 이미 취소된 예매 재취소 — 중복 발행 차단 (Lambda 좌석 카운터 이중 복구 방지)
    from common.errors import ReservationAlreadyCanceledError
    from reservation.domains.reservation.model import Reservation

    user_id = uuid4()
    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=user_id,
        event_id=uuid4(),
        reserved_num=1,
        is_canceled=True,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    with pytest.raises(ReservationAlreadyCanceledError):
        await service.requestCancel(user_id=user_id, reservation_id=reservation.reservation_id)

    sqs.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_occupied_seats_merges_db_and_redis_holds(coreSession, redis):
    from reservation.domains.reservation.model import Reservation
    from reservation.domains.reservation.service import _holdKey

    event_id = uuid4()
    # DB: 좌석 1(비취소), 좌석 2(취소 — 제외돼야 함)
    coreSession.add(
        Reservation(reservation_id=uuid4(), user_id=uuid4(), event_id=event_id, reserved_num=1),
    )
    coreSession.add(
        Reservation(
            reservation_id=uuid4(), user_id=uuid4(), event_id=event_id,
            reserved_num=2, is_canceled=True,
        ),
    )
    # 다른 이벤트 좌석 — 섞이면 안 됨
    coreSession.add(
        Reservation(reservation_id=uuid4(), user_id=uuid4(), event_id=uuid4(), reserved_num=9),
    )
    await coreSession.commit()

    # Redis: 미영속 hold — 좌석 5
    await redis.set(_holdKey(event_id, 5), str(uuid4()))

    service = ReservationReadService(coreSession, redis)
    occupied = await service.occupiedSeats(event_id)

    assert occupied == [1, 5]  # 취소(2)·타 이벤트(9) 제외, 정렬


@pytest.mark.asyncio
async def test_get_by_id_cache_miss_then_populates_cache(coreSession, redis):
    from reservation.domains.reservation.model import Reservation

    reservation = Reservation(
        reservation_id=uuid4(), user_id=uuid4(), event_id=uuid4(), reserved_num=2,
    )
    coreSession.add(reservation)
    await coreSession.commit()
    service = ReservationReadService(coreSession, redis)

    assert await redis.get(_reservationCacheKey(reservation.reservation_id)) is None
    read = await service.getById(reservation.reservation_id)

    assert read.reservation_id == reservation.reservation_id
    # 캐시 miss → DB 조회 후 적재되어야 함
    assert await redis.get(_reservationCacheKey(reservation.reservation_id)) is not None


@pytest.mark.asyncio
async def test_get_by_id_serves_from_cache_without_db(coreSession, redis):
    from reservation.domains.reservation.schema import ReservationRead

    # DB 에는 없지만 캐시에만 있는 경우 — 캐시 우선(cache hit) 동작 검증
    rid = uuid4()
    cached = ReservationRead(
        reservation_id=rid,
        user_id=uuid4(),
        event_id=uuid4(),
        is_canceled=False,
        reserved_num=9,
        created_at=date(2026, 6, 4),
        last_modified=None,
    )
    await redis.set(_reservationCacheKey(rid), cached.model_dump_json())
    service = ReservationReadService(coreSession, redis)

    read = await service.getById(rid)

    assert read.reserved_num == 9  # DB 조회 없이 캐시에서 반환


@pytest.mark.asyncio
async def test_request_cancel_invalidates_cache(coreSession, redis):
    from reservation.domains.reservation.model import Reservation

    user_id = uuid4()
    reservation = Reservation(
        reservation_id=uuid4(), user_id=user_id, event_id=uuid4(), reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    # 캐시 적재 후 취소 → 캐시 무효화 검증
    await ReservationReadService(coreSession, redis).getById(reservation.reservation_id)
    assert await redis.get(_reservationCacheKey(reservation.reservation_id)) is not None

    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    write = ReservationWriteService(
        event_client=FakeEventClient(),
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )
    await write.requestCancel(user_id=user_id, reservation_id=reservation.reservation_id)

    assert await redis.get(_reservationCacheKey(reservation.reservation_id)) is None


@pytest.mark.asyncio
async def test_request_create_populates_reservation_cache(coreSession, redis):
    # 생성 시 낙관적 캐시 적재 — Lambda DB write 전에도 결제 검증이 hit 하도록
    event_id = uuid4()
    event_client = FakeEventClient()
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    user_id = uuid4()
    service = ReservationWriteService(
        event_client=event_client,
        reservation_reader_session=coreSession,
        redis=redis,
        sqs=sqs,
    )

    reservation_id = await service.requestCreate(
        user_id=user_id,
        payload=ReservationCreate(event_id=event_id, reserved_num=3),
    )

    cached = await redis.get(_reservationCacheKey(reservation_id))
    assert cached is not None
    read = ReservationRead.model_validate_json(cached)
    assert read.user_id == user_id          # 소유자 검증용 필드 포함
    assert read.is_canceled is False
    assert read.reserved_num == 3
