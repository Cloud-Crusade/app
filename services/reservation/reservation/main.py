from common.app_factory import createApp
from config.settings import settings
from connector.pool import GrpcChannelPool
from connector.server import startServer
from fastapi import FastAPI

from reservation.clients import EventClient, setEventClient
from reservation.grpc_server import registerReservationService
from reservation.routers import captcha, health, queue, reservations


async def _startup(app: FastAPI) -> None:
    # 결제 서비스가 호출하는 gRPC 서버 + event 서비스 호출용 클라이언트 풀
    app.state.grpc_server = await startServer(
        registerReservationService, port=settings.grpc_port,
    )
    app.state.event_pool = GrpcChannelPool(settings.event_grpc_target)
    setEventClient(EventClient(app.state.event_pool))


async def _shutdown(app: FastAPI) -> None:
    await app.state.grpc_server.stop(grace=5)
    await app.state.event_pool.close()
    setEventClient(None)


routers = [health.router, reservations.router, captcha.router]
# 대기열은 운영에서 API Gateway → Lambda 가 처리 — dev/test 에서만 in-memory 스텁 등록
if settings.env in {"development", "test"}:
    routers.append(queue.router)

app = createApp(
    title="Reservation Service",
    routers=routers,
    on_startup=_startup,
    on_shutdown=_shutdown,
)
