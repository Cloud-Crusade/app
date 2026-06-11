from common.app_factory import createApp
from config.settings import settings
from connector.server import startServer
from fastapi import FastAPI

from event.grpc_server import registerEventService
from event.routers import events, health


async def _startup(app: FastAPI) -> None:
    # reservation 서비스가 좌석 검증을 위해 호출하는 gRPC 서버
    app.state.grpc_server = await startServer(registerEventService, port=settings.grpc_port)


async def _shutdown(app: FastAPI) -> None:
    await app.state.grpc_server.stop(grace=5)


app = createApp(
    title="Event Service",
    routers=[health.router, events.router],
    on_startup=_startup,
    on_shutdown=_shutdown,
)
