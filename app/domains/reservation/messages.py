"""SQS 메시지 페이로드 정의 — Lambda repo 와 공유하는 계약 (스키마 호환성 주의)."""
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MESSAGE_VERSION = 1


def _now() -> datetime:
    return datetime.now(UTC)


class ReservationCreateMessage(BaseModel):
    action: Literal["reservation.create"] = "reservation.create"
    version: int = MESSAGE_VERSION
    reservation_id: UUID
    user_id: UUID
    event_id: UUID
    reserved_num: int = Field(ge=1)
    issued_at: datetime = Field(default_factory=_now)


class ReservationCancelMessage(BaseModel):
    action: Literal["reservation.cancel"] = "reservation.cancel"
    version: int = MESSAGE_VERSION
    reservation_id: UUID
    user_id: UUID
    event_id: UUID  # Lambda 측 좌석 카운터 보정 및 SQS MessageGroupId 일관성 위해 포함
    # Lambda 가 seat:hold:{event_id}:{reserved_num} 키 구성해 해제
    reserved_num: int = Field(ge=1)
    issued_at: datetime = Field(default_factory=_now)
