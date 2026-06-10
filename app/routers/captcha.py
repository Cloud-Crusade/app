from fastapi import APIRouter

from app.common.captcha import CaptchaChallenge, buildChallenge

router = APIRouter(prefix="/captcha", tags=["captcha"])


@router.get(
    "/challenge",
    response_model=CaptchaChallenge,
    summary="ALTCHA PoW 캡차 챌린지 발급",
)
async def getCaptchaChallenge() -> CaptchaChallenge:
    return buildChallenge()
