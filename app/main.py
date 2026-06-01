import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.common.dev_bootstrap import initDevSchemaIfEnabled
from app.common.errors import DomainError
from app.common.exception_handlers import (
    domainErrorHandler,
    integrityErrorHandler,
    unhandledErrorHandler,
    validationErrorHandler,
)
from app.common.logging import configureLogging
from app.routers import auth, events, health, reservations, users
from app.settings import settings

configureLogging(env=settings.env)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await initDevSchemaIfEnabled()
    yield


app = FastAPI(
    title="Ticketing API",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "AWS 인프라 (EKS · RDS · ElastiCache · SQS · CloudWatch) 의 스파이크 흡수 능력을 "
        "검증하기 위한 티켓팅 서비스.\n\n"
        "기능 범위는 **인증 · 행사 관리 · 티켓팅** 으로 한정합니다.\n\n"
        "- Swagger UI: `/docs`\n"
        "- ReDoc: `/redoc`\n"
        "- OpenAPI JSON: `/openapi.json`"
    ),
    openapi_tags=[
        {"name": "auth", "description": "회원가입 · 로그인 · 토큰 갱신"},
        {"name": "users", "description": "사용자 프로필"},
        {"name": "events", "description": "행사 등록 · 조회 · 수정 · 삭제"},
        {
            "name": "reservations",
            "description": "예매 (write 는 SQS 비동기, read 는 동기)",
        },
        {"name": "health", "description": "헬스체크 (k8s probe · ALB target)"},
    ],
)


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
app.add_exception_handler(DomainError, domainErrorHandler)
app.add_exception_handler(RequestValidationError, validationErrorHandler)
app.add_exception_handler(IntegrityError, integrityErrorHandler)
app.add_exception_handler(Exception, unhandledErrorHandler)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)
app.include_router(reservations.router)
