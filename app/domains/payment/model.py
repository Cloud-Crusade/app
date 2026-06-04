from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.common.db import ReservationBase


class PaymentHistory(ReservationBase):
    __tablename__ = "payment_histories"

    payment_history_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    # 동일 RDS#2 의 reservations 참조 — 다만 비동기 Lambda write 의 insert 순서 결합을
    # 피하려 DB FK 제약 없이 인덱스만 둔다 (reservation 모델의 user/event 처리와 일관)
    reservation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[date] = mapped_column(
        Date,
        default=lambda: datetime.now().date(),
        server_default=func.current_date(),
        nullable=False,
    )
