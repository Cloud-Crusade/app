from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import getCoreReaderSession, getCoreWriterSession
from app.common.security import (
    decodeToken,
    issueAccessToken,
    issueRefreshToken,
)
from app.domains.user.schema import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    UserRead,
)
from app.domains.user.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    responses={
        409: {"description": "이미 사용 중인 사용자 이름"},
        422: {"description": "요청 검증 실패 (user_name 3~255자, password 8~72자)"},
    },
)
async def signup(
    payload: SignupRequest,
    session: Annotated[AsyncSession, Depends(getCoreWriterSession)],
) -> UserRead:
    user = await UserService(session).signup(payload)
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="로그인 (access + refresh 토큰 발급)",
    responses={401: {"description": "아이디 또는 비밀번호 불일치"}},
)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(getCoreReaderSession)],
) -> TokenPair:
    user = await UserService(session).authenticate(
        user_name=payload.user_name, password=payload.password,
    )
    return TokenPair(
        access_token=issueAccessToken(user.user_id),
        refresh_token=issueRefreshToken(user.user_id),
    )


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="refresh token 으로 새 토큰쌍 발급",
    responses={401: {"description": "만료·위조·access 토큰 오용"}},
)
async def refresh(payload: RefreshRequest) -> TokenPair:
    token = decodeToken(payload.refresh_token, expected_type="refresh")
    return TokenPair(
        access_token=issueAccessToken(token.user_id),
        refresh_token=issueRefreshToken(token.user_id),
    )
