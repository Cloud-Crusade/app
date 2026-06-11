from uuid import UUID, uuid4

import pytest
from common.security import issueAccessToken

# 서비스 분할: auth/event 는 별도 서비스 → 토큰은 직접 발급, Event 는 gRPC fake(conftest)로 응답
USER_ID = uuid4()


def _headers(user_id: UUID = USER_ID) -> dict[str, str]:
    return {"authorization": f"Bearer {issueAccessToken(user_id)}"}




@pytest.mark.asyncio
async def test_post_reservations_returns_202_with_reservation_id(client, sqsMock, coreSession):
    headers = _headers()
    event_id = str(uuid4())

    response = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 12},
        headers=headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "accepted"
    assert body["reservation_id"]
    sqsMock.publish.assert_awaited_once()
    kwargs = sqsMock.publish.await_args.kwargs
    assert kwargs["group_id"] == event_id  # FIFO group_id = event_id
    assert kwargs["dedup_id"] == body["reservation_id"]
    message = kwargs["message"]
    assert message["action"] == "reservation.create"
    assert message["event_id"] == event_id
    assert message["reserved_num"] == 12


@pytest.mark.asyncio
async def test_post_reservations_without_token_returns_401(client):
    response = await client.post(
        "/reservations",
        json={"event_id": "00000000-0000-0000-0000-000000000000", "reserved_num": 1},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_reservations_when_event_missing_returns_404(client, sqsMock):
    headers = _headers()
    response = await client.post(
        "/reservations",
        json={"event_id": "00000000-0000-0000-0000-000000000000", "reserved_num": 1},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "EVENT_NOT_FOUND"
    sqsMock.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_reservations_when_seat_taken_returns_409(client, sqsMock, coreSession):
    headers = _headers()
    event_id = str(uuid4())

    first = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 3},
        headers=headers,
    )
    assert first.status_code == 202

    second = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 3},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["code"] == "SEAT_ALREADY_TAKEN"
    # 첫 번째만 SQS publish, 두 번째는 publish 안 됨
    assert sqsMock.publish.await_count == 1


@pytest.mark.asyncio
async def test_post_reservations_invalid_reserved_num_returns_422(client, coreSession):
    headers = _headers()
    event_id = str(uuid4())
    response = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 0},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_reservation_publishes_cancel(client, sqsMock, coreSession):
    """수동으로 DB 에 reservation 을 넣은 후 cancel 호출."""
    from uuid import uuid4

    from reservation.domains.reservation.model import Reservation

    headers = _headers()
    # 인증된 사용자 user_id 추출
    user_id = USER_ID

    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=user_id,
        event_id=uuid4(),
        reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    response = await client.delete(
        f"/reservations/{reservation.reservation_id}",
        headers=headers,
    )

    assert response.status_code == 202
    sqsMock.publish.assert_awaited_once()
    kwargs = sqsMock.publish.await_args.kwargs
    assert kwargs["group_id"] == str(reservation.event_id)  # FIFO group_id = event_id
    assert kwargs["dedup_id"] == f"cancel:{reservation.reservation_id}"
    message = kwargs["message"]
    assert message["action"] == "reservation.cancel"
    assert message["reservation_id"] == str(reservation.reservation_id)
    assert message["event_id"] == str(reservation.event_id)
    assert message["reserved_num"] == reservation.reserved_num


@pytest.mark.asyncio
async def test_delete_other_users_reservation_returns_404(client, sqsMock, coreSession):
    from uuid import uuid4

    from reservation.domains.reservation.model import Reservation

    headers = _headers()
    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=uuid4(),  # 다른 사용자
        event_id=uuid4(),
        reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    response = await client.delete(
        f"/reservations/{reservation.reservation_id}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "RESERVATION_NOT_FOUND"
    sqsMock.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_occupied_seats_returns_db_and_hold_seats(client, coreSession, redis):
    from uuid import uuid4

    from reservation.domains.reservation.model import Reservation
    from reservation.domains.reservation.service import _holdKey

    headers = _headers()
    event_id = uuid4()
    coreSession.add(
        Reservation(reservation_id=uuid4(), user_id=uuid4(), event_id=event_id, reserved_num=4),
    )
    await coreSession.commit()
    await redis.set(_holdKey(event_id, 7), str(uuid4()))

    response = await client.get(
        "/reservations/seats/occupied",
        params={"event_id": str(event_id)},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["event_id"] == str(event_id)
    assert body["occupied"] == [4, 7]


@pytest.mark.asyncio
async def test_get_occupied_seats_without_token_returns_401(client):
    from uuid import uuid4

    response = await client.get(
        "/reservations/seats/occupied",
        params={"event_id": str(uuid4())},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_reservations_returns_only_mine(client, coreSession):
    from uuid import uuid4

    from reservation.domains.reservation.model import Reservation

    headers = _headers()
    user_id = USER_ID

    for i in range(2):
        coreSession.add(
            Reservation(
                reservation_id=uuid4(),
                user_id=user_id,
                event_id=uuid4(),
                reserved_num=i + 1,
            ),
        )
    # 다른 사용자 예매 — 응답에 포함되면 안 됨
    coreSession.add(
        Reservation(
            reservation_id=uuid4(),
            user_id=uuid4(),
            event_id=uuid4(),
            reserved_num=99,
        ),
    )
    await coreSession.commit()

    response = await client.get("/reservations", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["user_id"] == str(user_id) for item in body["items"])


@pytest.mark.asyncio
async def test_get_reservation_single_returns_404_for_other_owner(client, coreSession):
    from uuid import uuid4

    from reservation.domains.reservation.model import Reservation

    headers = _headers()
    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=uuid4(),  # 다른 사용자
        event_id=uuid4(),
        reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    response = await client.get(
        f"/reservations/{reservation.reservation_id}",
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_created_reservation_appears_in_list_before_db_persist(client, sqsMock, coreSession):
    """SQS→Lambda 미영속 상태에서도 per-user 캐시 인덱스 병합으로 목록에 노출."""
    headers = _headers()
    event_id = str(uuid4())

    create = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 2},
        headers=headers,
    )
    assert create.status_code == 202
    reservation_id = create.json()["reservation_id"]

    listed = await client.get("/reservations", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    ids = [item["reservation_id"] for item in body["items"]]
    assert reservation_id in ids
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_pending_reservation_self_heals_when_persisted(client, sqsMock, coreSession):
    """DB 영속(Lambda 처리 가정) 후에는 캐시 pending 과 중복 노출되지 않는다."""
    from uuid import UUID

    from reservation.domains.reservation.model import Reservation

    headers = _headers()
    event_id = str(uuid4())

    create = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 1},
        headers=headers,
    )
    reservation_id = create.json()["reservation_id"]

    # Lambda 가 동일 id 로 DB 에 영속했다고 가정
    coreSession.add(
        Reservation(
            reservation_id=UUID(reservation_id),
            user_id=USER_ID,
            event_id=UUID(event_id),
            reserved_num=1,
        ),
    )
    await coreSession.commit()

    listed = await client.get("/reservations", headers=headers)
    body = listed.json()
    ids = [item["reservation_id"] for item in body["items"]]
    assert ids.count(reservation_id) == 1
    assert body["total"] == 1
