from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from auth.db import getReaderSession

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe (프로세스 생존 확인)")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/readyz",
    summary="Readiness probe (core DB 의존성 검증)",
    responses={503: {"description": "의존성 미준비"}},
)
async def readiness(
    core: Annotated[AsyncSession, Depends(getReaderSession)],
) -> dict[str, str]:
    try:
        await core.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="not ready") from exc
    return {"status": "ready"}
