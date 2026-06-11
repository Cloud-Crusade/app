from uuid import UUID

import grpc
from ccproto.reservation.v1 import reservation_pb2, reservation_pb2_grpc
from connector.pool import GrpcChannelPool


class ReservationClient:
    """reservation 서비스 gRPC 클라이언트 — 풀링된 채널로 예매 소유자 조회 (#48: 직접호출 대체)."""

    def __init__(self, pool: GrpcChannelPool) -> None:
        self._pool = pool

    async def getOwnerId(self, reservation_id: UUID) -> UUID | None:
        stub = reservation_pb2_grpc.ReservationServiceStub(self._pool.channel())
        try:
            response = await stub.GetReservation(
                reservation_pb2.GetReservationRequest(reservation_id=str(reservation_id)),
            )
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return UUID(response.user_id)


_reservation_client: ReservationClient | None = None


def setReservationClient(client: ReservationClient | None) -> None:
    global _reservation_client
    _reservation_client = client


def getReservationClient() -> ReservationClient:
    if _reservation_client is None:
        raise RuntimeError("ReservationClient 미초기화 (lifespan startup 누락)")
    return _reservation_client
