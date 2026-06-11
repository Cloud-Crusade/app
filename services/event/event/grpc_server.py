from uuid import UUID

import grpc
from ccproto.event.v1 import event_pb2, event_pb2_grpc

from event.db import readerFactory
from event.domains.event.repository import EventRepository


class EventServicer(event_pb2_grpc.EventServiceServicer):
    async def GetEvent(
        self,
        request: event_pb2.GetEventRequest,
        context: grpc.aio.ServicerContext,
    ) -> event_pb2.GetEventResponse:
        try:
            event_id = UUID(request.event_id)
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid event_id")
        async with readerFactory() as session:
            event = await EventRepository(session).getById(event_id)
        if event is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "event not found")
        return event_pb2.GetEventResponse(
            event_id=str(event.event_id),
            total_seats=event.total_seats,
        )


def registerEventService(server: grpc.aio.Server) -> None:
    event_pb2_grpc.add_EventServiceServicer_to_server(EventServicer(), server)
