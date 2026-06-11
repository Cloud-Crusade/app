from common.captcha import CaptchaChallenge, buildChallenge
from fastapi import APIRouter

router = APIRouter(prefix="/captcha", tags=["captcha"])


@router.get(
    "/challenge",
    response_model=CaptchaChallenge,
    summary="ALTCHA PoW 캡차 챌린지 발급",
)
async def getCaptchaChallenge() -> CaptchaChallenge:
    return buildChallenge()
