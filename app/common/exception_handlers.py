import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.common.errors import DomainError

logger = structlog.get_logger()


async def domainErrorHandler(request: Request, exc: DomainError) -> JSONResponse:
    logger.warning(
        "domain_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


async def validationErrorHandler(
    request: Request, exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "요청 검증 실패",
            "details": exc.errors(),
        },
    )


async def integrityErrorHandler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.error("integrity_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=409,
        content={"code": "CONFLICT", "message": "데이터 충돌이 발생했습니다"},
    )


async def unhandledErrorHandler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "예상치 못한 오류"},
    )
