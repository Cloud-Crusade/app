from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.security import decodeToken

bearerScheme = HTTPBearer(
    bearerFormat="JWT",
    description="`POST /auth/login` 으로 발급받은 access token 을 입력합니다.",
)


async def getCurrentUserId(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearerScheme)],
) -> UUID:
    # 로컬 JWT 검증 — User 테이블 조회 없이 토큰에서 user_id 만 추출 (타 서비스는 User 미접근)
    payload = decodeToken(credentials.credentials, expected_type="access")
    return payload.user_id
