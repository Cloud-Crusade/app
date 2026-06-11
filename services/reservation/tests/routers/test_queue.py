from uuid import uuid4

import pytest
from common.security import issueAccessToken


def _authHeaders() -> dict[str, str]:
    return {"authorization": f"Bearer {issueAccessToken(uuid4())}"}


@pytest.mark.asyncio
async def test_get_queue_waits_then_completes_with_token(client):
    headers = _authHeaders()

    first = await client.get("/queue/ev-1", headers=headers)
    assert first.status_code == 200
    assert first.json()["code"] == "WAITING"
    assert first.json()["data"]["position"] >= 1

    last = first.json()
    for _ in range(10):
        response = await client.get("/queue/ev-1", headers=headers)
        last = response.json()
        if last["code"] == "COMPLETED":
            break

    assert last["code"] == "COMPLETED"
    assert last["data"]["token"]


@pytest.mark.asyncio
async def test_get_queue_without_token_returns_401(client):
    response = await client.get("/queue/ev-1")
    assert response.status_code == 401
