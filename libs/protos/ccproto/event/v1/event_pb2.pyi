from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class GetEventRequest(_message.Message):
    __slots__ = ("event_id",)
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    def __init__(self, event_id: _Optional[str] = ...) -> None: ...

class GetEventResponse(_message.Message):
    __slots__ = ("event_id", "total_seats")
    EVENT_ID_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SEATS_FIELD_NUMBER: _ClassVar[int]
    event_id: str
    total_seats: int
    def __init__(self, event_id: _Optional[str] = ..., total_seats: _Optional[int] = ...) -> None: ...
