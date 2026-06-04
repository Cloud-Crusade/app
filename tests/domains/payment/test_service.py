from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.common.errors import PaymentNotFoundError, ReservationNotFoundError
from app.domains.payment.model import PaymentHistory
from app.domains.payment.schema import PaymentCreate, PaymentRead
from app.domains.payment.service import (
    PaymentReadService,
    PaymentWriteService,
    _cacheKey,
    _userIndexKey,
)
from app.domains.reservation.model import Reservation
from app.domains.reservation.schema import ReservationRead
from app.domains.reservation.service import _reservationCacheKey


async def _seedReservation(session, *, user_id):
    reservation = Reservation(
        reservation_id=uuid4(), user_id=user_id, event_id=uuid4(), reserved_num=1,
    )
    session.add(reservation)
    await session.flush()
    return reservation


@pytest.mark.asyncio
async def test_request_create_succeeds_when_reservation_only_in_cache(coreSession, redis):
    # 예매가 아직 DB 에 없고 낙관적 캐시에만 있는 경우 — 결제가 캐시로 검증되어 발행됨
    user_id = uuid4()
    rid = uuid4()
    cached = ReservationRead(
        reservation_id=rid,
        user_id=user_id,
        event_id=uuid4(),
        is_canceled=False,
        reserved_num=1,
        created_at=date(2026, 6, 4),
        last_modified=None,
    )
    await redis.set(_reservationCacheKey(rid), cached.model_dump_json())
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = PaymentWriteService(
        reservation_reader_session=coreSession, redis=redis, sqs=sqs,
    )

    payment_history_id = await service.requestCreate(
        user_id=user_id,
        payload=PaymentCreate(reservation_id=rid, payment_method="mock"),
    )

    assert payment_history_id
    sqs.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_create_publishes_payment_message(coreSession, redis):
    user_id = uuid4()
    reservation = await _seedReservation(coreSession, user_id=user_id)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = PaymentWriteService(
        reservation_reader_session=coreSession, redis=redis, sqs=sqs,
    )

    payment_history_id = await service.requestCreate(
        user_id=user_id,
        payload=PaymentCreate(
            reservation_id=reservation.reservation_id, payment_method="mock",
        ),
    )

    assert payment_history_id
    sqs.publish.assert_awaited_once()
    kwargs = sqs.publish.await_args.kwargs
    assert kwargs["group_id"] == str(reservation.reservation_id)  # 같은 예매끼리 group
    assert kwargs["dedup_id"] == str(payment_history_id)
    message = kwargs["message"]
    assert message["action"] == "payment.create"
    assert message["payment_history_id"] == str(payment_history_id)
    assert message["payment_method"] == "mock"


@pytest.mark.asyncio
async def test_request_create_when_reservation_missing_raises(coreSession, redis):
    sqs = AsyncMock()
    service = PaymentWriteService(
        reservation_reader_session=coreSession, redis=redis, sqs=sqs,
    )

    with pytest.raises(ReservationNotFoundError):
        await service.requestCreate(
            user_id=uuid4(),
            payload=PaymentCreate(reservation_id=uuid4(), payment_method="mock"),
        )
    sqs.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_create_when_reservation_not_owned_raises(coreSession, redis):
    reservation = await _seedReservation(coreSession, user_id=uuid4())
    sqs = AsyncMock()
    service = PaymentWriteService(
        reservation_reader_session=coreSession, redis=redis, sqs=sqs,
    )

    with pytest.raises(ReservationNotFoundError):
        await service.requestCreate(
            user_id=uuid4(),  # 예매 소유자와 다른 사용자
            payload=PaymentCreate(
                reservation_id=reservation.reservation_id, payment_method="mock",
            ),
        )
    sqs.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_by_id_missing_raises(coreSession, redis):
    service = PaymentReadService(coreSession, redis)

    with pytest.raises(PaymentNotFoundError):
        await service.getById(uuid4())


@pytest.mark.asyncio
async def test_get_by_id_cache_miss_then_populates_cache(coreSession, redis):
    payment = PaymentHistory(
        payment_history_id=uuid4(),
        user_id=uuid4(),
        reservation_id=uuid4(),
        payment_method="mock",
    )
    coreSession.add(payment)
    await coreSession.commit()
    service = PaymentReadService(coreSession, redis)

    assert await redis.get(_cacheKey(payment.payment_history_id)) is None
    read = await service.getById(payment.payment_history_id)

    assert read.payment_history_id == payment.payment_history_id
    # 캐시 miss → DB 조회 후 적재되어야 함
    assert await redis.get(_cacheKey(payment.payment_history_id)) is not None


@pytest.mark.asyncio
async def test_get_by_id_serves_from_cache_without_db(coreSession, redis):
    # DB 에는 없지만 캐시에만 있는 경우 — 캐시 우선 동작 검증
    pid = uuid4()
    cached = PaymentRead(
        payment_history_id=pid,
        user_id=uuid4(),
        reservation_id=uuid4(),
        payment_method="card",
        created_at=date(2026, 6, 4),
    )
    await redis.set(_cacheKey(pid), cached.model_dump_json())
    service = PaymentReadService(coreSession, redis)

    read = await service.getById(pid)

    assert read.payment_method == "card"  # DB 조회 없이 캐시에서 반환


@pytest.mark.asyncio
async def test_request_create_populates_cache_and_user_index(coreSession, redis):
    # 생성 시 단건 캐시 + per-user 인덱스 적재 검증
    user_id = uuid4()
    reservation = await _seedReservation(coreSession, user_id=user_id)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    service = PaymentWriteService(
        reservation_reader_session=coreSession, redis=redis, sqs=sqs,
    )

    payment_id = await service.requestCreate(
        user_id=user_id,
        payload=PaymentCreate(
            reservation_id=reservation.reservation_id, payment_method="mock",
        ),
    )

    cached = await redis.get(_cacheKey(payment_id))
    assert cached is not None
    assert PaymentRead.model_validate_json(cached).user_id == user_id
    assert str(payment_id) in await redis.smembers(_userIndexKey(user_id))


@pytest.mark.asyncio
async def test_list_paged_includes_inflight_from_cache(coreSession, redis):
    # 아직 DB 에 없는(SQS 대기) 결제가 목록에 포함되어야 함
    user_id = uuid4()
    reservation = await _seedReservation(coreSession, user_id=user_id)
    sqs = AsyncMock()
    sqs.publish = AsyncMock(return_value="m")
    payment_id = await PaymentWriteService(
        reservation_reader_session=coreSession, redis=redis, sqs=sqs,
    ).requestCreate(
        user_id=user_id,
        payload=PaymentCreate(
            reservation_id=reservation.reservation_id, payment_method="mock",
        ),
    )

    items, total = await PaymentReadService(coreSession, redis).listPaged(
        page=1, size=20, user_id=user_id,
    )

    assert total == 1
    assert [p.payment_history_id for p in items] == [payment_id]


@pytest.mark.asyncio
async def test_list_paged_dedups_persisted_and_cleans_index(coreSession, redis):
    # 캐시+인덱스 에 있고 DB 에도 영속된 경우 — 중복 없이 1건, 인덱스 정리(self-heal)
    user_id = uuid4()
    payment = PaymentHistory(
        payment_history_id=uuid4(),
        user_id=user_id,
        reservation_id=uuid4(),
        payment_method="mock",
    )
    coreSession.add(payment)
    await coreSession.commit()

    pid = payment.payment_history_id
    cached = PaymentRead.model_validate(payment)
    await redis.set(_cacheKey(pid), cached.model_dump_json())
    await redis.sadd(_userIndexKey(user_id), str(pid))

    items, total = await PaymentReadService(coreSession, redis).listPaged(
        page=1, size=20, user_id=user_id,
    )

    assert total == 1
    assert len(items) == 1
    # 영속분은 인덱스에서 제거되어야 함
    assert str(pid) not in await redis.smembers(_userIndexKey(user_id))


@pytest.mark.asyncio
async def test_list_paged_offset_merge_paginates_across_cache_and_db(coreSession, redis):
    # pending(캐시) 1건 + DB 1건, size=1 → page1=pending, page2=db, total=2
    user_id = uuid4()
    db_payment = PaymentHistory(
        payment_history_id=uuid4(),
        user_id=user_id,
        reservation_id=uuid4(),
        payment_method="db",
    )
    coreSession.add(db_payment)
    await coreSession.commit()

    pending_id = uuid4()
    pending = PaymentRead(
        payment_history_id=pending_id,
        user_id=user_id,
        reservation_id=uuid4(),
        payment_method="pending",
        created_at=date(2026, 6, 4),
    )
    await redis.set(_cacheKey(pending_id), pending.model_dump_json())
    await redis.sadd(_userIndexKey(user_id), str(pending_id))

    service = PaymentReadService(coreSession, redis)
    page1, total1 = await service.listPaged(page=1, size=1, user_id=user_id)
    page2, total2 = await service.listPaged(page=2, size=1, user_id=user_id)

    assert total1 == total2 == 2
    assert [p.payment_history_id for p in page1] == [pending_id]   # 미영속이 최신
    assert [p.payment_history_id for p in page2] == [db_payment.payment_history_id]
