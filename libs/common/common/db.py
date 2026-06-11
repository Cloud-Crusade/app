from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func

from common.settings import settings

_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class CoreBase(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class ReservationBase(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )


def _buildEngine(url: str) -> AsyncEngine:
    # SQLite (테스트용) 는 풀 옵션을 받지 않음
    if url.startswith("sqlite"):
        return create_async_engine(url)
    return create_async_engine(
        url,
        pool_size=10,
        max_overflow=0,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=2,
    )


coreWriterEngine: AsyncEngine = _buildEngine(settings.core_writer_url)
coreReaderEngine: AsyncEngine = _buildEngine(settings.core_reader_url)
reservationWriterEngine: AsyncEngine = _buildEngine(settings.reservation_writer_url)
reservationReaderEngine: AsyncEngine = _buildEngine(settings.reservation_reader_url)

coreWriterFactory = async_sessionmaker(
    coreWriterEngine, expire_on_commit=False, class_=AsyncSession,
)
coreReaderFactory = async_sessionmaker(
    coreReaderEngine, expire_on_commit=False, class_=AsyncSession,
)
reservationWriterFactory = async_sessionmaker(
    reservationWriterEngine, expire_on_commit=False, class_=AsyncSession,
)
reservationReaderFactory = async_sessionmaker(
    reservationReaderEngine, expire_on_commit=False, class_=AsyncSession,
)
