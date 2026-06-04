from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentCreate(BaseModel):
    reservation_id: UUID
    payment_method: str = Field(min_length=1, max_length=20)


class PaymentAccepted(BaseModel):
    """비동기 write 의 즉시 응답 — Lambda 가 처리하기 전 단계의 payment_history_id."""

    payment_history_id: UUID
    status: str = "accepted"


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_history_id: UUID
    user_id: UUID
    reservation_id: UUID
    payment_method: str
    created_at: date


class PaymentPage(BaseModel):
    items: list[PaymentRead]
    total: int
    page: int
    size: int
