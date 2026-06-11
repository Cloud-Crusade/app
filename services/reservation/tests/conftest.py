from uuid import UUID

import pytest
from reservation.clients import getEventClient
from reservation.main import app as _app

# event 서비스 gRPC 는 테스트에서 호출하지 않는다 — getEventClient 를 fake 로 대체.
# zero-uuid 는 "이벤트 없음"(None), 그 외는 좌석 100석으로 응답.
_ZERO_UUID = UUID(int=0)


class _FakeEventClient:
    async def getTotalSeats(self, event_id: UUID) -> int | None:
        return None if event_id == _ZERO_UUID else 100


@pytest.fixture
def app():
    _app.dependency_overrides[getEventClient] = lambda: _FakeEventClient()
    return _app
