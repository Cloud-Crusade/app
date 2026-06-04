from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import PaymentNotFoundError, ReservationNotFoundError
from app.common.sqs import SqsPublisher
from app.domains.payment.messages import PaymentCreateMessage
from app.domains.payment.model import PaymentHistory
from app.domains.payment.repository import PaymentRepository
from app.domains.payment.schema import PaymentCreate, PaymentRead
from app.domains.reservation.service import ReservationReadService
from app.settings import settings

MAX_PAGE_SIZE = 100


def _cacheKey(payment_history_id: UUID) -> str:
    return f"payment:{payment_history_id}"


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
    ) -> tuple[list[PaymentHistory], int]:
        page = max(page, 1)
        size = max(1, min(size, MAX_PAGE_SIZE))
        return await self._payments.listPaged(page=page, size=size, user_id=user_id)


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
        return payment_history_id
