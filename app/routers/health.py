from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import (
    getCoreReaderSession,
    getRedisClient,
    getReservationReaderSession,
)

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe (프로세스 생존 확인)")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/readyz",
    summary="Readiness probe (DB · Redis 의존성 검증)",
    responses={503: {"description": "의존성 미준비"}},
)
async def readiness(
    core: Annotated[AsyncSession, Depends(getCoreReaderSession)],
    reservation: Annotated[AsyncSession, Depends(getReservationReaderSession)],
    redis: Annotated[Redis, Depends(getRedisClient)],
) -> dict[str, str]:
    try:
        await core.execute(text("SELECT 1"))
        await reservation.execute(text("SELECT 1"))
        await redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="not ready") from exc
    return {"status": "ready"}
