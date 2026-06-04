"""SQS 메시지 페이로드 정의 — Lambda repo 와 공유하는 계약 (스키마 호환성 주의)."""
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MESSAGE_VERSION = 1


def _now() -> datetime:
    return datetime.now(UTC)


class PaymentCreateMessage(BaseModel):
    action: Literal["payment.create"] = "payment.create"
    version: int = MESSAGE_VERSION
    payment_history_id: UUID
    user_id: UUID
    reservation_id: UUID
    payment_method: str
    issued_at: datetime = Field(default_factory=_now)
