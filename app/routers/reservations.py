from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import (
    getCoreReaderSession,
    getCurrentUser,
    getRedisClient,
    getReservationReaderSession,
    getReservationSqs,
)
from app.common.sqs import SqsPublisher
from app.domains.reservation.schema import (
    ReservationAccepted,
    ReservationCreate,
    ReservationPage,
    ReservationRead,
)
from app.domains.reservation.service import (
    ReservationReadService,
    ReservationWriteService,
)
from app.domains.user.model import User

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post(
    "",
    response_model=ReservationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="예매 요청 (비동기 — SQS 발행)",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "이벤트 없음"},
        409: {"description": "이미 선점된 좌석"},
        422: {"description": "요청 검증 실패"},
    },
)
async def createReservation(
    payload: ReservationCreate,
    user: Annotated[User, Depends(getCurrentUser)],
    core_reader: Annotated[AsyncSession, Depends(getCoreReaderSession)],
    reservation_reader: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
    sqs: Annotated[SqsPublisher, Depends(getReservationSqs)],
) -> ReservationAccepted:
    service = ReservationWriteService(
        core_reader_session=core_reader,
        reservation_reader_session=reservation_reader,
        redis=redis,
        sqs=sqs,
    )
    reservation_id = await service.requestCreate(user_id=user.user_id, payload=payload)
    return ReservationAccepted(reservation_id=reservation_id)


@router.delete(
    "/{reservation_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReservationAccepted,
    summary="예매 취소 요청 (비동기 — SQS 발행)",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "예매 없음 또는 본인 예약 아님"},
        409: {"description": "이미 취소된 예매"},
    },
)
async def cancelReservation(
    reservation_id: UUID,
    user: Annotated[User, Depends(getCurrentUser)],
    core_reader: Annotated[AsyncSession, Depends(getCoreReaderSession)],
    reservation_reader: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
    sqs: Annotated[SqsPublisher, Depends(getReservationSqs)],
) -> ReservationAccepted:
    service = ReservationWriteService(
        core_reader_session=core_reader,
        reservation_reader_session=reservation_reader,
        redis=redis,
        sqs=sqs,
    )
    await service.requestCancel(user_id=user.user_id, reservation_id=reservation_id)
    return ReservationAccepted(reservation_id=reservation_id)


@router.get(
    "",
    response_model=ReservationPage,
    summary="내 예매 목록 조회 (페이지네이션)",
    responses={401: {"description": "인증 필요"}},
)
async def listMyReservations(
    user: Annotated[User, Depends(getCurrentUser)],
    session: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReservationPage:
    items, total = await ReservationReadService(session, redis).listPaged(
        page=page,
        size=size,
        user_id=user.user_id,
    )
    return ReservationPage(items=items, total=total, page=page, size=size)


@router.get(
    "/{reservation_id}",
    response_model=ReservationRead,
    summary="예매 단건 조회",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "예매 없음 또는 본인 예약 아님"},
    },
)
async def getReservation(
    reservation_id: UUID,
    user: Annotated[User, Depends(getCurrentUser)],
    session: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
) -> ReservationRead:
    from app.common.errors import ReservationNotFoundError

    reservation = await ReservationReadService(session, redis).getById(reservation_id)
    if reservation.user_id != user.user_id:
        raise ReservationNotFoundError(reservation_id=str(reservation_id))
    return reservation
