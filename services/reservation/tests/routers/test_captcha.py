from uuid import uuid4

import pytest
from common.security import issueAccessToken
from config.settings import settings


def _authHeaders() -> dict[str, str]:
    return {"authorization": f"Bearer {issueAccessToken(uuid4())}"}


@pytest.mark.asyncio
async def test_challenge_endpoint_returns_altcha_fields(client):
    response = await client.get("/captcha/challenge")

    assert response.status_code == 200
    body = response.json()
    assert body["algorithm"] == "SHA-256"
    assert body["challenge"] and body["salt"] and body["signature"]


@pytest.mark.asyncio
async def test_create_reservation_without_captcha_when_enabled_returns_403(client, monkeypatch):
    monkeypatch.setattr(settings, "captcha_enabled", True)
    headers = _authHeaders()

    response = await client.post(
        "/reservations",
        json={"event_id": "00000000-0000-0000-0000-000000000001", "reserved_num": 1},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "CAPTCHA_FAILED"
