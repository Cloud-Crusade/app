from typing import Annotated

from config.settings import settings
from fastapi import Depends, Header
from redis.asyncio import Redis

from common.captcha import CHALLENGE_TTL_SECONDS, verifyPayload
from common.errors import CaptchaError
from common.redis import buildRedis
from common.sqs import SqsPublisher, getReservationSqsPublisher


def getRedisClient() -> Redis:
    return buildRedis()


def getReservationSqs() -> SqsPublisher:
    return getReservationSqsPublisher()


async def verifyReservationCaptcha(
    redis: Annotated[Redis, Depends(getRedisClient)],
    x_captcha_token: Annotated[str | None, Header()] = None,
) -> None:
    # 플래그 off(기본) 면 캡차를 요구하지 않는다
    if not settings.captcha_enabled:
        return
    # 활성인데 시크릿 미설정이면 빈 HMAC 키로 우회 가능 → fail-closed(차단)
    if not settings.captcha_hmac_secret:
        raise CaptchaError()
    if not x_captcha_token:
        raise CaptchaError()
    challenge = verifyPayload(x_captcha_token)
    if challenge is None:
        raise CaptchaError()
    # 같은 challenge 재사용(replay) 방지 — 최초 1회만 통과
    if not await redis.set(f"captcha:used:{challenge}", "1", nx=True, ex=CHALLENGE_TTL_SECONDS):
        raise CaptchaError()
