from uuid import uuid4

import pytest
from common.errors import InvalidTokenError
from common.security import (
    decodeToken,
    hashPassword,
    issueAccessToken,
    issueRefreshToken,
    verifyPassword,
)


def test_hash_and_verify_password_roundtrip():
    raw = "correct horse battery staple"
    hashed = hashPassword(raw)
    assert hashed != raw
    assert verifyPassword(raw, hashed) is True
    assert verifyPassword("wrong", hashed) is False


def test_access_token_decodes_with_matching_type():
    user_id = uuid4()
    token = issueAccessToken(user_id)
    payload = decodeToken(token, expected_type="access")
    assert payload.user_id == user_id
    assert payload.token_type == "access"


def test_refresh_token_decoded_as_access_raises():
    token = issueRefreshToken(uuid4())
    with pytest.raises(InvalidTokenError):
        decodeToken(token, expected_type="access")


def test_tampered_token_raises():
    token = issueAccessToken(uuid4()) + "x"
    with pytest.raises(InvalidTokenError):
        decodeToken(token, expected_type="access")
