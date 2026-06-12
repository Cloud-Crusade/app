from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReservationCreate(BaseModel):
    event_id: UUID
    reserved_num: int = Field(ge=1)


class ReservationAccepted(BaseModel):
    """비동기 write 의 즉시 응답 — Lambda 가 처리하기 전 단계의 reservation_id."""

    reservation_id: UUID
    status: str = "accepted"


class ReservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: UUID
    user_id: UUID
    event_id: UUID
    is_canceled: bool
    reserved_num: int
    created_at: date
    last_modified: date | None


class OccupiedSeats(BaseModel):
    """이벤트의 점유 좌석 번호 목록 — 클라이언트 좌석 선택용."""

    event_id: UUID
    occupied: list[int]


class ReservationPage(BaseModel):
    items: list[ReservationRead]
    total: int
    page: int
    size: int
