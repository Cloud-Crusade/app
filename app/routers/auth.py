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


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    session: Annotated[AsyncSession, Depends(getCoreWriterSession)],
) -> UserRead:
    user = await UserService(session).signup(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair)
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


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest) -> TokenPair:
    token = decodeToken(payload.refresh_token, expected_type="refresh")
    return TokenPair(
        access_token=issueAccessToken(token.user_id),
        refresh_token=issueRefreshToken(token.user_id),
    )
