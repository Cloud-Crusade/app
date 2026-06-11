from datetime import UTC, datetime

from config.settings import settings
from sqlalchemy import DateTime
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

# 서비스별 Base 가 공유하는 index/constraint 명명 규칙 (마이그레이션 일관성)
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )


def buildEngine(url: str) -> AsyncEngine:
    # SQLite (테스트용) 는 풀 옵션을 받지 않음
    if url.startswith("sqlite"):
        return create_async_engine(url)
    return create_async_engine(
        url,
        pool_size=10,
        max_overflow=0,
        pool_pre_ping=True,  # 죽은 커넥션 감지 → 새 커넥션은 DNS 재해석(엔드포인트 컷오버 흡수)
        pool_recycle=settings.db_pool_recycle_seconds,
        pool_timeout=2,
    )
