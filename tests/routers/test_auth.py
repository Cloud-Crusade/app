import pytest

SIGNUP_PAYLOAD = {"user_name": "alice", "password": "password1234"}
LOGIN_PAYLOAD = {"user_name": "alice", "password": "password1234"}


@pytest.mark.asyncio
async def test_signup_returns_201_and_user(client):
    response = await client.post("/auth/signup", json=SIGNUP_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["user_name"] == "alice"
    assert "user_id" in body
    assert "password" not in body
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_signup_too_long_password_returns_422(client):
    # schema 는 max_length=72 만 강제 (min_length 없음). 73자 초과 시 422.
    response = await client.post(
        "/auth/signup", json={"user_name": "alice", "password": "p" * 73},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_signup_duplicate_returns_409(client):
    await client.post("/auth/signup", json=SIGNUP_PAYLOAD)
    response = await client.post(
        "/auth/signup", json={"user_name": "alice", "password": "anothereone"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_USER_NAME"


@pytest.mark.asyncio
async def test_login_returns_token_pair(client):
    await client.post("/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post("/auth/login", json=LOGIN_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client):
    await client.post("/auth/signup", json=SIGNUP_PAYLOAD)

    response = await client.post(
        "/auth/login", json={"user_name": "alice", "password": "wrongwrong"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_returns_new_token_pair(client):
    await client.post("/auth/signup", json=SIGNUP_PAYLOAD)
    login = await client.post("/auth/login", json=LOGIN_PAYLOAD)
    refresh_token = login.json()["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"]


@pytest.mark.asyncio
async def test_refresh_with_access_token_returns_401(client):
    await client.post("/auth/signup", json=SIGNUP_PAYLOAD)
    login = await client.post("/auth/login", json=LOGIN_PAYLOAD)
    access_token = login.json()["access_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_get_me_returns_user(client):
    await client.post("/auth/signup", json=SIGNUP_PAYLOAD)
    login = await client.post("/auth/login", json=LOGIN_PAYLOAD)
    access_token = login.json()["access_token"]

    response = await client.get(
        "/users/me", headers={"authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["user_name"] == "alice"


@pytest.mark.asyncio
async def test_get_me_without_token_returns_401(client):
    # HTTPBearer: Authorization 헤더 미존재 시 401 + WWW-Authenticate: Bearer (RFC 7235)
    response = await client.get("/users/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_get_me_with_invalid_token_returns_401(client):
    response = await client.get(
        "/users/me", headers={"authorization": "Bearer not-a-jwt"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"
