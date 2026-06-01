import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.common.errors import DomainError
from app.common.logging import configureLogging
from app.routers import auth, health, users
from app.settings import settings

configureLogging(env=settings.env)
logger = structlog.get_logger()

app = FastAPI(title="Ticketing API")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


app.add_middleware(RequestIdMiddleware)


@app.exception_handler(DomainError)
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


@app.exception_handler(RequestValidationError)
async def validationErrorHandler(
    request: Request, exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": "요청 검증 실패", "details": exc.errors()},
    )


@app.exception_handler(IntegrityError)
async def integrityErrorHandler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.error("integrity_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=409,
        content={"code": "CONFLICT", "message": "데이터 충돌이 발생했습니다"},
    )


@app.exception_handler(Exception)
async def unhandledErrorHandler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "예상치 못한 오류"},
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
