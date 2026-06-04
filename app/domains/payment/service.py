from datetime import UTC, datetime
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import PaymentNotFoundError, ReservationNotFoundError
from app.common.sqs import SqsPublisher
from app.domains.payment.messages import PaymentCreateMessage
from app.domains.payment.repository import PaymentRepository
from app.domains.payment.schema import PaymentCreate, PaymentRead
from app.domains.reservation.service import ReservationReadService
from app.settings import settings

MAX_PAGE_SIZE = 100


def _cacheKey(payment_history_id: UUID | str) -> str:
    return f"payment:{payment_history_id}"


def _userIndexKey(user_id: UUID) -> str:
    return f"payment:user:{user_id}"


class PaymentReadService:
    """조회 — 단건은 캐시 우선(Redis) + DB 폴백(cache-aside), 목록은 DB 직결."""

    def __init__(self, reader_session: AsyncSession, redis: Redis) -> None:
        self._payments = PaymentRepository(reader_session)
        self._redis = redis

    async def getById(self, payment_history_id: UUID) -> PaymentRead:
        cache_key = _cacheKey(payment_history_id)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            return PaymentRead.model_validate_json(cached)

        payment = await self._payments.getById(payment_history_id)
        if payment is None:
            raise PaymentNotFoundError(payment_history_id=str(payment_history_id))

        read = PaymentRead.model_validate(payment)
        # 결제 기록은 불변(수정·취소 없음)이라 무효화 없이 TTL 만으로 충분
        await self._redis.set(
            cache_key, read.model_dump_json(), ex=settings.payment_cache_ttl_seconds,
        )
        return read

    async def listPaged(
        self, *, page: int, size: int, user_id: UUID | None = None,
    ) -> tuple[list[PaymentRead], int]:
        page = max(page, 1)
        size = max(1, min(size, MAX_PAGE_SIZE))
        offset = (page - 1) * size

        # 미영속(SQS 대기) 결제는 캐시에만 존재 → DB 와 병합. 가상 리스트 [pending ++ db].
        pending = await self._pendingPayments(user_id) if user_id is not None else []
        pending_count = len(pending)

        db_offset = max(0, offset - pending_count)
        db_items, db_total = await self._payments.listByOffset(
            offset=db_offset, limit=size, user_id=user_id,
        )
        db_reads = [PaymentRead.model_validate(p) for p in db_items]

        window: list[PaymentRead] = []
        if offset < pending_count:
            window.extend(pending[offset : offset + size])
        window.extend(db_reads[: size - len(window)])
        return window, db_total + pending_count

    async def _pendingPayments(self, user_id: UUID) -> list[PaymentRead]:
        # per-user 인덱스에서 미영속 결제만 추림. DB 영속분·만료분은 인덱스에서 정리(self-heal).
        index_key = _userIndexKey(user_id)
        ids = await self._redis.smembers(index_key)
        if not ids:
            return []

        pending: list[PaymentRead] = []
        stale: list[str] = []
        for member in ids:
            pid = member.decode() if isinstance(member, bytes) else member
            cached = await self._redis.get(_cacheKey(pid))
            if cached is None:
                stale.append(pid)
            else:
                pending.append(PaymentRead.model_validate_json(cached))

        if pending:
            persisted = await self._payments.existingIds(
                [p.payment_history_id for p in pending],
            )
            persisted_str = {str(pid) for pid in persisted}
            stale.extend(
                str(p.payment_history_id)
                for p in pending
                if str(p.payment_history_id) in persisted_str
            )
            pending = [
                p for p in pending if str(p.payment_history_id) not in persisted_str
            ]

        if stale:
            await self._redis.srem(index_key, *stale)

        pending.sort(
            key=lambda p: (p.created_at, str(p.payment_history_id)), reverse=True,
        )
        return pending


class PaymentWriteService:
    """비동기 write — 결제 기록을 SQS 에 발행. 실제 DB write 는 Lambda 가 수행."""

    def __init__(
        self,
        *,
        reservation_reader_session: AsyncSession,
        redis: Redis,
        sqs: SqsPublisher,
    ) -> None:
        # reservation service 의 캐시 우선 조회를 재사용 (cache hit 우선 → DB 폴백)
        self._reservations = ReservationReadService(reservation_reader_session, redis)
        self._redis = redis
        self._sqs = sqs

    async def requestCreate(self, *, user_id: UUID, payload: PaymentCreate) -> UUID:
        # 결제 대상 예매 존재 검증 — 없으면 ReservationNotFoundError (캐시 우선 조회)
        reservation = await self._reservations.getById(payload.reservation_id)
        # 본인 소유 검증 — 없는 예매를 SQS 에 넣지 않도록 사전 차단
        if reservation.user_id != user_id:
            raise ReservationNotFoundError(reservation_id=str(payload.reservation_id))

        payment_history_id = uuid4()
        message = PaymentCreateMessage(
            payment_history_id=payment_history_id,
            user_id=user_id,
            reservation_id=payload.reservation_id,
            payment_method=payload.payment_method,
        )
        # group_id = reservation_id → 같은 예매의 결제 메시지 순서 보장
        await self._sqs.publish(
            message=message.model_dump(mode="json"),
            group_id=str(payload.reservation_id),
            dedup_id=str(payment_history_id),
        )

        # 낙관적 캐시 적재 — Lambda DB write 전에도 단건/다건 조회가 반영하도록.
        # 결제 기록은 불변이라 무효화 없이 TTL 만으로 충분. 목록용 per-user 인덱스도 함께 갱신.
        optimistic = PaymentRead(
            payment_history_id=payment_history_id,
            user_id=user_id,
            reservation_id=payload.reservation_id,
            payment_method=payload.payment_method,
            created_at=datetime.now(UTC).date(),
        )
        await self._redis.set(
            _cacheKey(payment_history_id),
            optimistic.model_dump_json(),
            ex=settings.payment_cache_ttl_seconds,
        )
        index_key = _userIndexKey(user_id)
        await self._redis.sadd(index_key, str(payment_history_id))
        await self._redis.expire(index_key, settings.payment_cache_ttl_seconds)
        return payment_history_id
