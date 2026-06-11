from typing import Annotated
from uuid import UUID

from common.deps import (
    getRedisClient,
    getReservationReaderSession,
    getReservationSqs,
)
from common.errors import PaymentNotFoundError
from common.sqs import SqsPublisher
from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import getCurrentUser
from app.domains.payment.schema import (
    PaymentAccepted,
    PaymentCreate,
    PaymentPage,
    PaymentRead,
)
from app.domains.payment.service import PaymentReadService, PaymentWriteService
from app.domains.user.model import User

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    response_model=PaymentAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="결제 요청 (비동기 — SQS 발행)",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "예매 없음 또는 본인 예약 아님"},
        422: {"description": "요청 검증 실패"},
    },
)
async def createPayment(
    payload: PaymentCreate,
    user: Annotated[User, Depends(getCurrentUser)],
    reservation_reader: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
    sqs: Annotated[SqsPublisher, Depends(getReservationSqs)],
) -> PaymentAccepted:
    service = PaymentWriteService(
        reservation_reader_session=reservation_reader, redis=redis, sqs=sqs,
    )
    payment_history_id = await service.requestCreate(user_id=user.user_id, payload=payload)
    return PaymentAccepted(payment_history_id=payment_history_id)


@router.get(
    "",
    response_model=PaymentPage,
    summary="내 결제 내역 목록 조회 (페이지네이션)",
    responses={401: {"description": "인증 필요"}},
)
async def listMyPayments(
    user: Annotated[User, Depends(getCurrentUser)],
    session: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaymentPage:
    items, total = await PaymentReadService(session, redis).listPaged(
        page=page, size=size, user_id=user.user_id,
    )
    return PaymentPage(items=items, total=total, page=page, size=size)


@router.get(
    "/{payment_history_id}",
    response_model=PaymentRead,
    summary="결제 내역 단건 조회 (캐시 우선)",
    responses={
        401: {"description": "인증 필요"},
        404: {"description": "결제 내역 없음 또는 본인 것 아님"},
    },
)
async def getPayment(
    payment_history_id: UUID,
    user: Annotated[User, Depends(getCurrentUser)],
    session: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
) -> PaymentRead:
    payment = await PaymentReadService(session, redis).getById(payment_history_id)
    if payment.user_id != user.user_id:
        raise PaymentNotFoundError(payment_history_id=str(payment_history_id))
    return payment
