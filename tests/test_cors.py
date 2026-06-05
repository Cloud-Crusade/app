import pytest

ALLOWED_ORIGIN = "http://localhost:5173"


@pytest.mark.asyncio
async def test_preflight_options_allows_configured_origin(client):
    response = await client.options(
        "/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_preflight_does_not_allow_unknown_origin(client):
    response = await client.options(
        "/auth/login",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers.get("access-control-allow-origin") != "http://evil.example.com"
