from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from reservation.db import Base


class Reservation(Base):
    __tablename__ = "reservations"

    reservation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    is_canceled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false",
    )
    reserved_num: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[date] = mapped_column(
        Date,
        default=lambda: datetime.now().date(),
        server_default=func.current_date(),
        nullable=False,
    )
    last_modified: Mapped[date | None] = mapped_column(
        Date,
        onupdate=lambda: datetime.now().date(),
        nullable=True,
    )
