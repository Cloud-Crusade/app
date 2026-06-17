from uuid import uuid4

import pytest
from common.security import issueAccessToken

SAMPLE_EVENT = {
    "title": "공연 A",
    "body": "본문",
    "schedule": {
        "start_at": "2026-12-01T19:00:00+00:00",
        "end_at": "2026-12-01T21:00:00+00:00",
    },
    "img_urls": ["https://cdn.example.com/a.jpg"],
    "total_seats": 100,
}


def _authHeaders() -> dict[str, str]:
    return {"authorization": f"Bearer {issueAccessToken(uuid4())}"}


@pytest.mark.asyncio
async def test_create_event_returns_201(client):
    headers = _authHeaders()

    response = await client.post("/events", json=SAMPLE_EVENT, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "공연 A"
    assert "event_id" in body
    assert "user_id" in body


@pytest.mark.asyncio
async def test_create_event_without_token_returns_401(client):
    response = await client.post("/events", json=SAMPLE_EVENT)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_event_too_long_title_returns_422(client):
    headers = _authHeaders()
    payload = {**SAMPLE_EVENT, "title": "x" * 21}

    response = await client.post("/events", json=payload, headers=headers)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_create_event_invalid_schedule_returns_422(client):
    headers = _authHeaders()
    payload = {
        **SAMPLE_EVENT,
        "schedule": {
            "start_at": "2026-12-01T21:00:00+00:00",
            "end_at": "2026-12-01T19:00:00+00:00",
        },
    }

    response = await client.post("/events", json=payload, headers=headers)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_events_returns_page(client):
    headers = _authHeaders()
    for _ in range(3):
        await client.post("/events", json=SAMPLE_EVENT, headers=headers)

    response = await client.get("/events")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["page"] == 1
    assert body["size"] == 20


@pytest.mark.asyncio
async def test_get_event_returns_single(client):
    headers = _authHeaders()
    created = (await client.post("/events", json=SAMPLE_EVENT, headers=headers)).json()

    response = await client.get(f"/events/{created['event_id']}")

    assert response.status_code == 200
    assert response.json()["event_id"] == created["event_id"]


@pytest.mark.asyncio
async def test_get_event_missing_returns_404(client):
    response = await client.get("/events/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["code"] == "EVENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_patch_event_updates_title(client):
    headers = _authHeaders()
    created = (await client.post("/events", json=SAMPLE_EVENT, headers=headers)).json()

    response = await client.patch(
        f"/events/{created['event_id']}",
        json={"title": "공연 변경"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["title"] == "공연 변경"


@pytest.mark.asyncio
async def test_patch_event_missing_returns_404(client):
    headers = _authHeaders()
    response = await client.patch(
        "/events/00000000-0000-0000-0000-000000000000",
        json={"title": "x"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_event_returns_204(client):
    headers = _authHeaders()
    created = (await client.post("/events", json=SAMPLE_EVENT, headers=headers)).json()

    response = await client.delete(f"/events/{created['event_id']}", headers=headers)
    assert response.status_code == 204

    follow_up = await client.get(f"/events/{created['event_id']}")
    assert follow_up.status_code == 404


@pytest.mark.asyncio
async def test_delete_event_missing_returns_404(client):
    headers = _authHeaders()
    response = await client.delete(
        "/events/00000000-0000-0000-0000-000000000000", headers=headers,
    )
    assert response.status_code == 404
