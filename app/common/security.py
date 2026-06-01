from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.common.errors import InvalidTokenError
from app.settings import settings


def hashPassword(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verifyPassword(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))


@dataclass(frozen=True)
class TokenPayload:
    user_id: UUID
    token_type: str   # "access" | "refresh"


def _issue(user_id: UUID, *, token_type: str, ttl_seconds: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def issueAccessToken(user_id: UUID) -> str:
    return _issue(user_id, token_type="access", ttl_seconds=settings.jwt_access_ttl_seconds)


def issueRefreshToken(user_id: UUID) -> str:
    return _issue(user_id, token_type="refresh", ttl_seconds=settings.jwt_refresh_ttl_seconds)


def decodeToken(token: str, *, expected_type: str) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc
    if raw.get("type") != expected_type:
        raise InvalidTokenError()
    try:
        return TokenPayload(user_id=UUID(raw["sub"]), token_type=raw["type"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError() from exc
