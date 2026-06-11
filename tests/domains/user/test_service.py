import pytest
from common.errors import DuplicateUserNameError, InvalidCredentialsError

from app.domains.user.schema import SignupRequest
from app.domains.user.service import UserService


@pytest.mark.asyncio
async def test_signup_creates_user(coreSession):
    service = UserService(coreSession)

    user = await service.signup(SignupRequest(user_name="alice", password="password1234"))

    assert user.user_id
    assert user.user_name == "alice"
    assert user.password_hash != "password1234"


@pytest.mark.asyncio
async def test_signup_duplicate_user_name_raises(coreSession):
    service = UserService(coreSession)
    await service.signup(SignupRequest(user_name="alice", password="password1234"))

    with pytest.raises(DuplicateUserNameError):
        await service.signup(SignupRequest(user_name="alice", password="otherpassword"))


@pytest.mark.asyncio
async def test_authenticate_with_correct_password_returns_user(coreSession):
    service = UserService(coreSession)
    created = await service.signup(SignupRequest(user_name="alice", password="password1234"))

    authed = await service.authenticate(user_name="alice", password="password1234")

    assert authed.user_id == created.user_id


@pytest.mark.asyncio
async def test_authenticate_with_wrong_password_raises(coreSession):
    service = UserService(coreSession)
    await service.signup(SignupRequest(user_name="alice", password="password1234"))

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(user_name="alice", password="wrongpassword")


@pytest.mark.asyncio
async def test_authenticate_unknown_user_raises(coreSession):
    service = UserService(coreSession)

    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(user_name="ghost", password="password1234")
