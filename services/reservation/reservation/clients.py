from uuid import UUID

import grpc
from ccproto.event.v1 import event_pb2, event_pb2_grpc
from connector.pool import GrpcChannelPool


class EventClient:
    """event 서비스 gRPC 클라이언트 — 풀링된 채널로 좌석 정보 조회 (#48: 직접호출 대체)."""

    def __init__(self, pool: GrpcChannelPool) -> None:
        self._pool = pool

    async def getTotalSeats(self, event_id: UUID) -> int | None:
        stub = event_pb2_grpc.EventServiceStub(self._pool.channel())
        try:
            response = await stub.GetEvent(event_pb2.GetEventRequest(event_id=str(event_id)))
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise
        return response.total_seats


_event_client: EventClient | None = None


def setEventClient(client: EventClient | None) -> None:
    global _event_client
    _event_client = client


def getEventClient() -> EventClient:
    if _event_client is None:
        raise RuntimeError("EventClient 미초기화 (lifespan startup 누락)")
    return _event_client
