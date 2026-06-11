import base64
import hashlib
import json

import pytest
from common import captcha
from common.captcha import CaptchaChallenge
from config.settings import settings


def _solve(challenge: CaptchaChallenge) -> str:
    # PoW — maxnumber 까지 해시가 일치하는 number 를 탐색해 토큰을 만든다
    number = next(
        n
        for n in range(challenge.maxnumber + 1)
        if hashlib.sha256(f"{challenge.salt}{n}".encode()).hexdigest() == challenge.challenge
    )
    payload = {
        "algorithm": challenge.algorithm,
        "challenge": challenge.challenge,
        "number": number,
        "salt": challenge.salt,
        "signature": challenge.signature,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.fixture(autouse=True)
def _captcha_config(monkeypatch):
    monkeypatch.setattr(settings, "captcha_hmac_secret", "test-secret")
    monkeypatch.setattr(settings, "captcha_complexity", 500)


def test_verify_payload_accepts_valid_pow():
    challenge = captcha.buildChallenge()
    token = _solve(challenge)
    assert captcha.verifyPayload(token) == challenge.challenge


def test_verify_payload_rejects_tampered_number():
    challenge = captcha.buildChallenge()
    data = json.loads(base64.b64decode(_solve(challenge)))
    data["number"] += 1
    tampered = base64.b64encode(json.dumps(data).encode()).decode()
    assert captcha.verifyPayload(tampered) is None


def test_verify_payload_rejects_expired(monkeypatch):
    token = _solve(captcha.buildChallenge())
    monkeypatch.setattr(captcha.time, "time", lambda: 9_999_999_999)
    assert captcha.verifyPayload(token) is None


def test_verify_payload_rejects_garbage():
    assert captcha.verifyPayload("not-a-valid-token") is None
