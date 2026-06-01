import structlog
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from app.common.db import (
    CoreBase,
    ReservationBase,
    coreWriterEngine,
    reservationWriterEngine,
)
from app.settings import settings

logger = structlog.get_logger()

# 자동 스키마 생성은 dev/test 환경 한정 — 운영(production·staging) 절대 호출 금지
DEV_ENVS = frozenset({"development", "test"})


async def _createAll(engine: AsyncEngine, base: type[DeclarativeBase]) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)


async def initDevSchemaIfEnabled() -> None:
    if settings.env not in DEV_ENVS:
        logger.info("dev_schema_init_skipped", env=settings.env)
        return
    await _createAll(coreWriterEngine, CoreBase)
    await _createAll(reservationWriterEngine, ReservationBase)
    logger.info(
        "dev_schema_initialized",
        env=settings.env,
        core_tables=sorted(CoreBase.metadata.tables.keys()),
        reservation_tables=sorted(ReservationBase.metadata.tables.keys()),
    )
