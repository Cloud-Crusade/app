from common.app_factory import createApp
from config.settings import settings
from connector.pool import GrpcChannelPool
from fastapi import FastAPI

from payment.clients import ReservationClient, setReservationClient
from payment.db import Base, writerEngine
from payment.routers import health, payments


async def _startup(app: FastAPI) -> None:
    # reservation 서비스 호출용 클라이언트 풀 (payment 는 gRPC 서버 없음 — 클라이언트만)
    app.state.reservation_pool = GrpcChannelPool(settings.reservation_grpc_target)
    setReservationClient(ReservationClient(app.state.reservation_pool))


async def _shutdown(app: FastAPI) -> None:
    await app.state.reservation_pool.close()
    setReservationClient(None)


app = createApp(
    title="Payment Service",
    routers=[health.router, payments.router],
    dev_schema=(Base.metadata, writerEngine),
    on_startup=_startup,
    on_shutdown=_shutdown,
)
