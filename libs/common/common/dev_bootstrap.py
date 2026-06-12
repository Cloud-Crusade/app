import structlog
from config.settings import settings
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger()

# 자동 스키마 생성은 dev/test 환경 한정 — 운영(production·staging) 절대 호출 금지
DEV_ENVS = frozenset({"development", "test"})


async def initDevSchemaIfEnabled(metadata: MetaData, engine: AsyncEngine) -> None:
    if settings.env not in DEV_ENVS:
        logger.info("dev_schema_init_skipped", env=settings.env)
        return
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    logger.info("dev_schema_initialized", env=settings.env, tables=sorted(metadata.tables.keys()))
