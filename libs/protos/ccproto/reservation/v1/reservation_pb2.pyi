from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class GetReservationRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class GetReservationResponse(_message.Message):
    __slots__ = ("reservation_id", "user_id")
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    user_id: str
    def __init__(self, reservation_id: _Optional[str] = ..., user_id: _Optional[str] = ...) -> None: ...
