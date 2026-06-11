from uuid import UUID

import grpc
from ccproto.reservation.v1 import reservation_pb2, reservation_pb2_grpc
from common.db import reservationReaderFactory
from common.errors import ReservationNotFoundError
from common.redis import buildRedis

from reservation.domains.reservation.service import ReservationReadService


class ReservationServicer(reservation_pb2_grpc.ReservationServiceServicer):
    async def GetReservation(
        self,
        request: reservation_pb2.GetReservationRequest,
        context: grpc.aio.ServicerContext,
    ) -> reservation_pb2.GetReservationResponse:
        async with reservationReaderFactory() as session:
            service = ReservationReadService(session, buildRedis())
            try:
                reservation = await service.getById(UUID(request.reservation_id))
            except ReservationNotFoundError:
                await context.abort(grpc.StatusCode.NOT_FOUND, "reservation not found")
        return reservation_pb2.GetReservationResponse(
            reservation_id=str(reservation.reservation_id),
            user_id=str(reservation.user_id),
        )


def registerReservationService(server: grpc.aio.Server) -> None:
    reservation_pb2_grpc.add_ReservationServiceServicer_to_server(
        ReservationServicer(), server,
    )
