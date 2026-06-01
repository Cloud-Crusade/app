from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import (
    EventNotFoundError,
    ReservationNotFoundError,
    SeatAlreadyTakenError,
)
from app.common.sqs import SqsPublisher
from app.domains.event.repository import EventRepository
from app.domains.reservation.messages import (
    ReservationCancelMessage,
    ReservationCreateMessage,
)
from app.domains.reservation.model import Reservation
from app.domains.reservation.repository import ReservationRepository
from app.domains.reservation.schema import ReservationCreate
from app.settings import settings

MAX_PAGE_SIZE = 100


def _holdKey(event_id: UUID, reserved_num: int) -> str:
    return f"seat:hold:{event_id}:{reserved_num}"


class ReservationReadService:
    """동기 RDS 조회만 담당."""

    def __init__(self, reader_session: AsyncSession) -> None:
        self._reservations = ReservationRepository(reader_session)

    async def getById(self, reservation_id: UUID) -> Reservation:
        reservation = await self._reservations.getById(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id=str(reservation_id))
        return reservation

    async def listPaged(
        self, *, page: int, size: int, user_id: UUID | None = None,
    ) -> tuple[list[Reservation], int]:
        page = max(page, 1)
        size = max(1, min(size, MAX_PAGE_SIZE))
        return await self._reservations.listPaged(page=page, size=size, user_id=user_id)


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
        self, *, user_id: UUID, payload: ReservationCreate,
    ) -> UUID:
        # 1. 이벤트 존재 검증 (core RDS read)
        event = await self._events.getById(payload.event_id)
        if event is None:
            raise EventNotFoundError(event_id=str(payload.event_id))

        # 2. Redis 좌석 hold (SETNX + TTL)
        key = _holdKey(payload.event_id, payload.reserved_num)
        acquired = await self._redis.set(
            key, str(user_id), nx=True, ex=settings.seat_hold_ttl_seconds,
        )
        if not acquired:
            raise SeatAlreadyTakenError(
                event_id=str(payload.event_id),
                reserved_num=payload.reserved_num,
            )

        # 3. reservation_id 미리 발급 + SQS publish
        reservation_id = uuid4()
        try:
            message = ReservationCreateMessage(
                reservation_id=reservation_id,
                user_id=user_id,
                event_id=payload.event_id,
                reserved_num=payload.reserved_num,
            )
            await self._sqs.publish(
                message=message.model_dump(mode="json"),
                group_id=str(reservation_id),
                dedup_id=str(reservation_id),
            )
        except Exception:
            # SQS publish 실패 시 hold 즉시 해제 (보상)
            await self._redis.delete(key)
            raise

        return reservation_id

    async def requestCancel(self, *, user_id: UUID, reservation_id: UUID) -> None:
        # reservation 존재 확인 (read RDS)
        reservation = await self._reservations.getById(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id=str(reservation_id))

        # 본인 예약만 취소 가능 (단순 owner check)
        if reservation.user_id != user_id:
            raise ReservationNotFoundError(reservation_id=str(reservation_id))

        message = ReservationCancelMessage(
            reservation_id=reservation_id,
            user_id=user_id,
        )
        # 같은 reservation 의 create→cancel 이 같은 group → 순서 보장
        await self._sqs.publish(
            message=message.model_dump(mode="json"),
            group_id=str(reservation_id),
            dedup_id=f"cancel:{reservation_id}",
        )
