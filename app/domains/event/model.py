from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, Date, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.common.db import CoreBase

# 운영(Postgres)은 JSONB, 테스트(SQLite) 등은 일반 JSON 으로 fallback
_JsonField = JSON().with_variant(JSONB(), "postgresql")


class Event(CoreBase):
    __tablename__ = "events"

    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule: Mapped[dict] = mapped_column(_JsonField, nullable=False)
    img_urls: Mapped[list] = mapped_column(_JsonField, nullable=False, default=list)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)

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
