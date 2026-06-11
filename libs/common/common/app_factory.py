import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any

import structlog
from config.settings import settings
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from common.dev_bootstrap import initDevSchemaIfEnabled
from common.errors import DomainError
from common.exception_handlers import (
    domainErrorHandler,
    integrityErrorHandler,
    unhandledErrorHandler,
    validationErrorHandler,
)
from common.logging import configureLogging


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


def createApp(
    *,
    title: str,
    routers: Sequence[APIRouter],
    on_startup: Callable[[FastAPI], Awaitable[None]] | None = None,
    on_shutdown: Callable[[FastAPI], Awaitable[None]] | None = None,
    **kwargs: Any,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await initDevSchemaIfEnabled()
        if on_startup is not None:
            await on_startup(app)
        try:
            yield
        finally:
            if on_shutdown is not None:
                await on_shutdown(app)

    configureLogging(env=settings.env)
    app = FastAPI(title=title, version="0.1.0", lifespan=lifespan, **kwargs)
    app.add_middleware(RequestIdMiddleware)
    # CORS 는 가장 바깥에서 preflight(OPTIONS)를 먼저 처리하도록 마지막에 등록
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_exception_handler(DomainError, domainErrorHandler)
    app.add_exception_handler(RequestValidationError, validationErrorHandler)
    app.add_exception_handler(IntegrityError, integrityErrorHandler)
    app.add_exception_handler(Exception, unhandledErrorHandler)
    for router in routers:
        app.include_router(router)
    return app
