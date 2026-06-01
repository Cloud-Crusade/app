import pytest

SIGNUP = {"user_name": "alice", "password": "password1234"}
SAMPLE_EVENT = {
    "title": "공연 A",
    "body": "본문",
    "schedule": {
        "start_at": "2026-12-01T19:00:00+00:00",
        "end_at": "2026-12-01T21:00:00+00:00",
    },
    "img_urls": [],
}


async def _login(client) -> dict[str, str]:
    await client.post("/auth/signup", json=SIGNUP)
    login = await client.post("/auth/login", json=SIGNUP)
    return {"authorization": f"Bearer {login.json()['access_token']}"}


async def _createEvent(client, headers) -> str:
    response = await client.post("/events", json=SAMPLE_EVENT, headers=headers)
    return response.json()["event_id"]


@pytest.mark.asyncio
async def test_post_reservations_returns_202_with_reservation_id(client, sqsMock):
    headers = await _login(client)
    event_id = await _createEvent(client, headers)

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
    message = sqsMock.publish.await_args.kwargs["message"]
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
    headers = await _login(client)
    response = await client.post(
        "/reservations",
        json={"event_id": "00000000-0000-0000-0000-000000000000", "reserved_num": 1},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "EVENT_NOT_FOUND"
    sqsMock.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_reservations_when_seat_taken_returns_409(client, sqsMock):
    headers = await _login(client)
    event_id = await _createEvent(client, headers)

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
async def test_post_reservations_invalid_reserved_num_returns_422(client):
    headers = await _login(client)
    event_id = await _createEvent(client, headers)
    response = await client.post(
        "/reservations",
        json={"event_id": event_id, "reserved_num": 0},
        headers=headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delete_reservation_publishes_cancel(client, sqsMock, coreSession):
    """수동으로 DB 에 reservation 을 넣은 후 cancel 호출."""
    from uuid import UUID, uuid4

    from app.domains.reservation.model import Reservation

    headers = await _login(client)
    # 인증된 사용자 user_id 추출
    me = (await client.get("/users/me", headers=headers)).json()
    user_id = UUID(me["user_id"])

    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=user_id,
        event_id=uuid4(),
        reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    response = await client.delete(
        f"/reservations/{reservation.reservation_id}", headers=headers,
    )

    assert response.status_code == 202
    sqsMock.publish.assert_awaited_once()
    message = sqsMock.publish.await_args.kwargs["message"]
    assert message["action"] == "reservation.cancel"
    assert message["reservation_id"] == str(reservation.reservation_id)


@pytest.mark.asyncio
async def test_delete_other_users_reservation_returns_404(client, sqsMock, coreSession):
    from uuid import uuid4

    from app.domains.reservation.model import Reservation

    headers = await _login(client)
    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=uuid4(),  # 다른 사용자
        event_id=uuid4(),
        reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    response = await client.delete(
        f"/reservations/{reservation.reservation_id}", headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "RESERVATION_NOT_FOUND"
    sqsMock.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_my_reservations_returns_only_mine(client, coreSession):
    from uuid import UUID, uuid4

    from app.domains.reservation.model import Reservation

    headers = await _login(client)
    me = (await client.get("/users/me", headers=headers)).json()
    user_id = UUID(me["user_id"])

    for i in range(2):
        coreSession.add(
            Reservation(
                reservation_id=uuid4(), user_id=user_id, event_id=uuid4(), reserved_num=i + 1,
            ),
        )
    # 다른 사용자 예매 — 응답에 포함되면 안 됨
    coreSession.add(
        Reservation(
            reservation_id=uuid4(), user_id=uuid4(), event_id=uuid4(), reserved_num=99,
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

    from app.domains.reservation.model import Reservation

    headers = await _login(client)
    reservation = Reservation(
        reservation_id=uuid4(),
        user_id=uuid4(),  # 다른 사용자
        event_id=uuid4(),
        reserved_num=1,
    )
    coreSession.add(reservation)
    await coreSession.commit()

    response = await client.get(
        f"/reservations/{reservation.reservation_id}", headers=headers,
    )

    assert response.status_code == 404
