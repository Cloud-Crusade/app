"""ALTCHA 호환 proof-of-work CAPTCHA — 외부 서비스/라이브러리 의존 없이 stdlib 로 구현.

흐름: 서버가 challenge(salt + 서버만 아는 number 의 해시 + HMAC 서명) 발급 →
클라이언트가 PoW 로 number 를 brute-force(해시 일치) → 서버가 해시·HMAC 서명·만료를 검증.
검증은 전부 로컬 계산이며 외부 HTTP 호출이 없다. 재사용(replay) 방지는 호출 측이 Redis 로 처리.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from pydantic import BaseModel

from app.settings import settings

ALGORITHM = "SHA-256"
CHALLENGE_TTL_SECONDS = 300


class CaptchaChallenge(BaseModel):
    algorithm: str
    challenge: str
    maxnumber: int
    salt: str
    signature: str


def _sha256Hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sign(challenge: str) -> str:
    return hmac.new(
        settings.captcha_hmac_secret.encode(), challenge.encode(), hashlib.sha256
    ).hexdigest()


def buildChallenge() -> CaptchaChallenge:
    # number 는 PoW 정답 — 클라이언트가 brute-force 로 찾는다(maxnumber 가 난이도)
    number = secrets.randbelow(settings.captcha_complexity)
    expires = int(time.time()) + CHALLENGE_TTL_SECONDS
    salt = f"{secrets.token_hex(12)}.{expires}"
    challenge = _sha256Hex(salt + str(number))
    return CaptchaChallenge(
        algorithm=ALGORITHM,
        challenge=challenge,
        maxnumber=settings.captcha_complexity,
        salt=salt,
        signature=_sign(challenge),
    )


def verifyPayload(token: str) -> str | None:
    """유효하면 재사용 방지 키로 쓸 challenge 해시를 반환, 무효면 None."""
    try:
        data: Any = json.loads(base64.b64decode(token))
    except (ValueError, binascii.Error):
        return None
    if not isinstance(data, dict) or data.get("algorithm") != ALGORITHM:
        return None

    salt = data.get("salt")
    number = data.get("number")
    challenge = data.get("challenge")
    signature = data.get("signature")
    if not isinstance(salt, str) or not isinstance(number, int):
        return None
    if not isinstance(challenge, str) or not isinstance(signature, str):
        return None

    # 만료 확인 (salt 끝의 expires 타임스탬프)
    try:
        expires = int(salt.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return None
    if time.time() > expires:
        return None

    # PoW(해시 일치) + 서버 서명(HMAC) 검증 — 상수시간 비교
    if not hmac.compare_digest(_sha256Hex(salt + str(number)), challenge):
        return None
    if not hmac.compare_digest(_sign(challenge), signature):
        return None
    return challenge
