from typing import Annotated

from fastapi import APIRouter, Depends

from auth.deps import getCurrentUser
from auth.domains.user.model import User
from auth.domains.user.schema import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="현재 로그인 사용자 정보",
    responses={
        401: {"description": "Authorization 헤더 누락 또는 유효하지 않은 access token"},
        404: {"description": "토큰의 사용자가 존재하지 않음"},
    },
)
async def getMe(user: Annotated[User, Depends(getCurrentUser)]) -> UserRead:
    return UserRead.model_validate(user)
