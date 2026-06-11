from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from common.security import decodeToken

# auto_error=False + 명시적 401: 헤더 부재 시 응답(401 + WWW-Authenticate: Bearer)을
# FastAPI 기본 동작에 의존하지 않고 고정한다(버전 변화에도 안정, RFC 7235)
bearerScheme = HTTPBearer(
    bearerFormat="JWT",
    auto_error=False,
    description="`POST /auth/login` 으로 발급받은 access token 을 입력합니다.",
)


def unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def getCurrentUserId(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearerScheme)],
) -> UUID:
    # 로컬 JWT 검증 — User 테이블 조회 없이 토큰에서 user_id 만 추출 (타 서비스는 User 미접근)
    if credentials is None:
        raise unauthenticated()
    payload = decodeToken(credentials.credentials, expected_type="access")
    return payload.user_id
