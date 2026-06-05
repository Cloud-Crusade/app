from datetime import UTC, datetime
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import (
    EventNotFoundError,
    EventSoldOutError,
    ReservationAlreadyCanceledError,
    ReservationNotFoundError,
    SeatAlreadyTakenError,
    SeatOutOfRangeError,
)
from app.common.sqs import SqsPublisher
from app.domains.event.repository import EventRepository
from app.domains.reservation.messages import (
    ReservationCancelMessage,
    ReservationCreateMessage,
)
from app.domains.reservation.repository import ReservationRepository
from app.domains.reservation.schema import ReservationCreate, ReservationRead
from app.settings import settings

MAX_PAGE_SIZE = 100


def _holdKeyPrefix(event_id: UUID) -> str:
    return f"seat:hold:{event_id}:"


def _holdKey(event_id: UUID, reserved_num: int) -> str:
    return f"{_holdKeyPrefix(event_id)}{reserved_num}"


def _remainKey(event_id: UUID) -> str:
    return f"seats:remain:{event_id}"


def _reservationCacheKey(reservation_id: UUID | str) -> str:
    return f"reservation:{reservation_id}"


def _userIndexKey(user_id: UUID) -> str:
    return f"reservation:user:{user_id}"


class ReservationReadService:
    """RDS 조회 — 단건은 캐시 우선(Redis) + DB 폴백(cache-aside).

    redis 가 주입되면 단건 조회가 캐시 우선으로, 목록 조회가 미영속(SQS 대기) 예매를
    per-user 인덱스에서 병합한다. redis 가 없으면 목록은 DB 직결로 폴백한다.
    캐시 value 는 전체 ReservationRead 라 user_id 도 포함 → 결제 소유자 검증에 그대로 쓰인다.
    """

    def __init__(self, reader_session: AsyncSession, redis: Redis | None = None) -> None:
        self._reservations = ReservationRepository(reader_session)
        self._redis = redis

    async def getById(self, reservation_id: UUID) -> ReservationRead:
        cache_key = _reservationCacheKey(reservation_id)
        if self._redis is not None:
            cached = await self._redis.get(cache_key)
            if cached is not None:
                return ReservationRead.model_validate_json(cached)

        reservation = await self._reservations.getById(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id=str(reservation_id))

        read = ReservationRead.model_validate(reservation)
        # 예매는 취소로 변경 가능 → cancel 시 무효화(requestCancel) + 짧은 TTL 로 staleness 제한
        if self._redis is not None:
            await self._redis.set(
                cache_key,
                read.model_dump_json(),
                ex=settings.reservation_cache_ttl_seconds,
            )
        return read

    async def listPaged(
        self,
        *,
        page: int,
        size: int,
        user_id: UUID | None = None,
    ) -> tuple[list[ReservationRead], int]:
        page = max(page, 1)
        size = max(1, min(size, MAX_PAGE_SIZE))
        offset = (page - 1) * size

        # 미영속(SQS 대기) 예매는 캐시에만 존재 → DB 와 병합. 가상 리스트 [pending ++ db].
        pending = (
            await self._pendingReservations(user_id)
            if (self._redis is not None and user_id is not None)
            else []
        )
        pending_count = len(pending)

        db_offset = max(0, offset - pending_count)
        db_items, db_total = await self._reservations.listByOffset(
            offset=db_offset,
            limit=size,
            user_id=user_id,
        )
        db_reads = [ReservationRead.model_validate(r) for r in db_items]

        window: list[ReservationRead] = []
        if offset < pending_count:
            window.extend(pending[offset : offset + size])
        window.extend(db_reads[: size - len(window)])
        return window, db_total + pending_count

    async def occupiedSeats(self, event_id: UUID) -> list[int]:
        # 점유 좌석 = DB 비취소 예매 + Redis 활성 hold(미영속분 포함) 합집합
        occupied = await self._reservations.occupiedSeatNumbers(event_id)
        if self._redis is not None:
            prefix = _holdKeyPrefix(event_id)
            async for key in self._redis.scan_iter(match=f"{prefix}*", count=100):
                raw = key.decode() if isinstance(key, bytes) else key
                suffix = raw.rsplit(":", 1)[-1]
                if suffix.isdigit():
                    occupied.add(int(suffix))
        return sorted(occupied)

    async def _pendingReservations(self, user_id: UUID) -> list[ReservationRead]:
        # per-user 인덱스에서 미영속 예매만 추림. DB 영속분·만료분은 인덱스에서 정리(self-heal).
        assert self._redis is not None
        index_key = _userIndexKey(user_id)
        ids = await self._redis.smembers(index_key)
        if not ids:
            return []

        pending: list[ReservationRead] = []
        stale: list[str] = []
        for member in ids:
            rid = member.decode() if isinstance(member, bytes) else member
            cached = await self._redis.get(_reservationCacheKey(rid))
            if cached is None:
                stale.append(rid)
            else:
                pending.append(ReservationRead.model_validate_json(cached))

        if pending:
            persisted = await self._reservations.existingIds(
                [r.reservation_id for r in pending],
            )
            persisted_str = {str(rid) for rid in persisted}
            stale.extend(
                str(r.reservation_id) for r in pending if str(r.reservation_id) in persisted_str
            )
            pending = [r for r in pending if str(r.reservation_id) not in persisted_str]

        if stale:
            await self._redis.srem(index_key, *stale)

        pending.sort(key=lambda r: (r.created_at, str(r.reservation_id)), reverse=True)
        return pending


class ReservationWriteService:
    """비동기 write — Redis 좌석 hold + SQS publish. 실제 DB 변경은 Lambda 가 수행."""

    def __init__(
        self,
        *,
        core_reader_session: AsyncSession,
        reservation_reader_session: AsyncSession,
        redis: Redis,
        sqs: SqsPublisher,
    ) -> None:
        self._events = EventRepository(core_reader_session)
        self._reservations = ReservationRepository(reservation_reader_session)
        self._redis = redis
        self._sqs = sqs

    async def requestCreate(
        self,
        *,
        user_id: UUID,
        payload: ReservationCreate,
    ) -> UUID:
        # 1. 이벤트 존재 검증 (core RDS read)
        event = await self._events.getById(payload.event_id)
        if event is None:
            raise EventNotFoundError(event_id=str(payload.event_id))

        # 2. 좌석 번호 범위 검증 — 존재하지 않는 좌석을 SQS 에 넣지 않도록 사전 차단
        if not 1 <= payload.reserved_num <= event.total_seats:
            raise SeatOutOfRangeError(
                event_id=str(payload.event_id),
                reserved_num=payload.reserved_num,
                total_seats=event.total_seats,
            )

        # 3. Redis 잔여 카운터 (lazy init + 원자적 DECR) — 매진 차단
        remain_key = _remainKey(payload.event_id)
        await self._redis.set(remain_key, event.total_seats, nx=True)
        remain = await self._redis.decr(remain_key)
        if remain < 0:
            await self._redis.incr(remain_key)  # 복구
            raise EventSoldOutError(event_id=str(payload.event_id))

        # 4. Redis 좌석 hold (SETNX + TTL) — 동일 좌석 동시 점유 차단
        hold_key = _holdKey(payload.event_id, payload.reserved_num)
        acquired = await self._redis.set(
            hold_key,
            str(user_id),
            nx=True,
            ex=settings.seat_hold_ttl_seconds,
        )
        if not acquired:
            # 좌석 hold 실패 → 잔여 카운터 복구 (실제 점유는 다른 사용자)
            await self._redis.incr(remain_key)
            raise SeatAlreadyTakenError(
                event_id=str(payload.event_id),
                reserved_num=payload.reserved_num,
            )

        # 5. reservation_id 미리 발급 + SQS publish
        reservation_id = uuid4()
        try:
            message = ReservationCreateMessage(
                reservation_id=reservation_id,
                user_id=user_id,
                event_id=payload.event_id,
                reserved_num=payload.reserved_num,
            )
            # group_id = event_id → 같은 이벤트의 메시지가 한 group 으로 묶여 순서 보장
            # (인기 이벤트는 한 group 의 throughput 제한 적용, Lambda 측 좌석 충돌 처리에 유리)
            await self._sqs.publish(
                message=message.model_dump(mode="json"),
                group_id=str(payload.event_id),
                dedup_id=str(reservation_id),
            )
        except Exception:
            # SQS publish 실패 시 hold + 카운터 양방향 보상
            await self._redis.delete(hold_key)
            await self._redis.incr(remain_key)
            raise

        # 낙관적 캐시 적재 — Lambda 가 DB 에 쓰기 전에도 결제 검증(getById)이 hit 하도록.
        # created_at 은 요청 시각 기준(Lambda 의 current_date 와 거의 일치), 취소 시 무효화됨.
        optimistic = ReservationRead(
            reservation_id=reservation_id,
            user_id=user_id,
            event_id=payload.event_id,
            is_canceled=False,
            reserved_num=payload.reserved_num,
            created_at=datetime.now(UTC).date(),
            last_modified=None,
        )
        await self._redis.set(
            _reservationCacheKey(reservation_id),
            optimistic.model_dump_json(),
            ex=settings.reservation_cache_ttl_seconds,
        )
        # 목록용 per-user 인덱스 — 미영속 예매를 listPaged 가 병합해 노출
        index_key = _userIndexKey(user_id)
        await self._redis.sadd(index_key, str(reservation_id))
        await self._redis.expire(index_key, settings.reservation_cache_ttl_seconds)

        return reservation_id

    async def _loadForCancel(self, reservation_id: UUID) -> ReservationRead:
        # cache-first — 미영속(SQS 대기) 예매는 DB 에 없고 캐시에만 존재하므로 캐시 우선 조회.
        # 캐시 value 는 전체 ReservationRead 라 user_id·is_canceled 까지 그대로 검증에 쓰인다.
        cached = await self._redis.get(_reservationCacheKey(reservation_id))
        if cached is not None:
            return ReservationRead.model_validate_json(cached)

        reservation = await self._reservations.getById(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id=str(reservation_id))
        return ReservationRead.model_validate(reservation)

    async def requestCancel(self, *, user_id: UUID, reservation_id: UUID) -> None:
        reservation = await self._loadForCancel(reservation_id)

        # 본인 예약만 취소 가능 (단순 owner check — 미존재와 동일하게 404 로 가린다)
        if reservation.user_id != user_id:
            raise ReservationNotFoundError(reservation_id=str(reservation_id))

        # 이미 취소된 예매 재취소 차단 — 중복 cancel 발행 시 Lambda 가 좌석 카운터를 이중 복구
        if reservation.is_canceled:
            raise ReservationAlreadyCanceledError(reservation_id=str(reservation_id))

        message = ReservationCancelMessage(
            reservation_id=reservation_id,
            user_id=user_id,
            event_id=reservation.event_id,
            reserved_num=reservation.reserved_num,
        )
        # group_id = event_id → 같은 이벤트의 create→cancel 이 한 group 으로 묶여 순서 보장
        await self._sqs.publish(
            message=message.model_dump(mode="json"),
            group_id=str(reservation.event_id),
            dedup_id=f"cancel:{reservation_id}",
        )
        # 취소 요청 즉시 단건 캐시 무효화 + per-user 인덱스에서 제거 (best-effort)
        await self._redis.delete(_reservationCacheKey(reservation_id))
        await self._redis.srem(_userIndexKey(user_id), str(reservation_id))
