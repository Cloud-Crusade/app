# API 라우터 · 엔드포인트 구현 표준

## 핵심 원칙

> **간략화 우선** — 한 엔드포인트는 한 가지 일만. 응답 wrapper·envelope·HATEOAS 같은 메타 구조 도입 금지. service 결과를 Pydantic 스키마로 검증해 그대로 반환한다.

## APIRouter 분할 정책

### 규칙
- **파일 1개 = 도메인 1개** — `routers/reservations.py` 는 `Reservation` 관련 엔드포인트만
- **prefix · tags 는 라우터 생성 시 지정** — 엔드포인트마다 반복 금지
- **인증·페이지네이션 같은 공통 의존성**은 router 또는 path 레벨 `dependencies=`

```python
# app/routers/reservations.py
from fastapi import APIRouter, Depends

from app.common.deps import getCurrentUser

router = APIRouter(
    prefix="/reservations",
    tags=["reservations"],
    dependencies=[Depends(getCurrentUser)],
)
```

### main.py 등록

```python
# app/main.py
from fastapi import FastAPI

from app.routers import auth, events, payments, reservations, users

app = FastAPI(title="Ticketing API")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)
app.include_router(reservations.router)
app.include_router(payments.router)
```

## HTTP 메서드 · 경로 · 상태 코드

### 표준

| 동작 | 메서드 | 경로 패턴 | 성공 상태 |
|---|---|---|---|
| 목록 조회 | GET | `/events` | 200 |
| 단건 조회 | GET | `/events/{event_id}` | 200 |
| 생성 | POST | `/reservations` | 201 |
| 수정 (전체) | PUT | `/users/me` | 200 |
| 수정 (부분) | PATCH | `/users/me` | 200 |
| 삭제 | DELETE | `/reservations/{reservation_id}` | 204 |

### 규칙
- **경로 변수는 snake_case** — `{event_id}`, `{reservation_id}` (Pydantic·SQLAlchemy 와 일치)
- **컬렉션은 복수형** — `/events`, `/reservations`
- **하위 자원은 중첩** — `/events/{event_id}/seats`
- **명사만, 동사 금지** — `/login` 같은 인증 흐름은 `tag` 기준 예외 허용 (`/auth/login`)

## Pydantic 스키마 패턴

### 분리 원칙
- **요청 / 응답 / DB 모델은 각각 분리**
- 한 도메인의 스키마는 `domains/<name>/schema.py` 에 모두 모아둔다

```python
# app/domains/event/schema.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    venue: str = Field(min_length=1, max_length=200)
    starts_at: datetime
    total_seats: int = Field(gt=0)


class EventCreate(EventBase):
    pass


class EventRead(EventBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    available_seats: int
    created_at: datetime
```

### 규칙
- **`from_attributes=True`** 로 ORM 객체에서 직접 변환
- **요청 스키마는 `Field()` 로 제약** — 길이·범위·정규식
- **응답 스키마에 내부 필드 노출 금지** — `password_hash` 같은 필드는 절대 응답 모델에 포함하지 않음
- **공통 필드는 `*Base` 로 추출**, 상속은 1단계까지만

### `response_model` 사용

```python
@router.get("/{event_id}", response_model=EventRead)
async def getEvent(event_id: int, session=Depends(getCoreReaderSession)) -> EventRead:
    event = await EventService(session).getById(event_id)
    return EventRead.model_validate(event)
```

- **`response_model` 명시 필수** — OpenAPI 스펙·직렬화 검증 동시 처리
- 응답 데이터는 service 가 ORM 객체 또는 dict 로 반환하고, router 가 `model_validate` 로 변환

## 의존성 주입 (Depends)

### 표준 의존성 목록

| 의존성 | 위치 | 용도 |
|---|---|---|
| `getCoreWriterSession` | `common/deps.py` | RDS #1 writer (user/event 변경) |
| `getCoreReaderSession` | `common/deps.py` | RDS #1 reader (user/event 조회) |
| `getReservationWriterSession` | `common/deps.py` | RDS #2 writer (reservation/payment 변경) |
| `getReservationReaderSession` | `common/deps.py` | RDS #2 reader (reservation/payment 조회) |
| `getRedisClient` | `common/deps.py` | Redis (좌석 hold, 잔여 카운터) |
| `getCurrentUser` | `common/deps.py` | JWT 검증 + User 조회 |

### DB 세션 의존성

```python
# app/common/deps.py
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.db import (
    coreWriterFactory, coreReaderFactory,
    reservationWriterFactory, reservationReaderFactory,
)


async def getCoreWriterSession() -> AsyncIterator[AsyncSession]:
    async with coreWriterFactory() as session:
        yield session


async def getCoreReaderSession() -> AsyncIterator[AsyncSession]:
    async with coreReaderFactory() as session:
        yield session


async def getReservationWriterSession() -> AsyncIterator[AsyncSession]:
    async with reservationWriterFactory() as session:
        yield session


async def getReservationReaderSession() -> AsyncIterator[AsyncSession]:
    async with reservationReaderFactory() as session:
        yield session
```

### 인증 의존성

```python
# app/common/deps.py
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import InvalidTokenError, UserNotFoundError
from app.common.security import decodeAccessToken
from app.domains.user.repository import UserRepository
from app.domains.user.model import User


async def getCurrentUser(
    authorization: str = Header(...),
    session: AsyncSession = Depends(getCoreReaderSession),
) -> User:
    if not authorization.startswith("Bearer "):
        raise InvalidTokenError()
    token = authorization.removeprefix("Bearer ")
    payload = decodeAccessToken(token)
    user = await UserRepository(session).getById(payload.user_id)
    if user is None:
        raise UserNotFoundError(user_id=payload.user_id)
    return user
```

### 규칙
- **의존성 함수는 `getXxx` 형식** — 메서드 네이밍 규칙(camelCase) 과 일관
- **의존성 안에서 비즈니스 로직 금지** — 인증·세션 같은 횡단 관심사만
- **의존성 함수는 `common/deps.py` 한 곳에** — 여기저기 흩어 놓지 않음

## JWT 인증

### 토큰 정책
- **access token**: 30 분 (`jwt_access_ttl_seconds`)
- **refresh token**: 14 일 (`jwt_refresh_ttl_seconds`)
- **알고리즘**: HS256 (대칭키)
- **claim**: `sub` (user_id), `exp`, `iat`, `type` (`access`|`refresh`)

### 보호 라우트 정의

```python
# 단일 엔드포인트 보호
@router.get("/me", response_model=UserRead)
async def getMe(user: User = Depends(getCurrentUser)) -> UserRead:
    return UserRead.model_validate(user)


# 라우터 전체 보호 (위에서 본 패턴)
router = APIRouter(
    prefix="/reservations",
    tags=["reservations"],
    dependencies=[Depends(getCurrentUser)],
)
```

### 토큰 발급 흐름

```python
# app/routers/auth.py
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import getCoreReaderSession
from app.common.security import issueAccessToken, issueRefreshToken
from app.domains.user.schema import LoginRequest, TokenPair
from app.domains.user.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(getCoreReaderSession),
) -> TokenPair:
    user = await UserService(session).authenticate(payload.email, payload.password)
    return TokenPair(
        access_token=issueAccessToken(user.id),
        refresh_token=issueRefreshToken(user.id),
    )
```

### 보안 원칙
- **access token 은 헤더로만 전달** — 쿼리스트링·바디 전달 금지
- **refresh token 은 HTTPS 전용 쿠키 또는 안전한 저장소 권장** — 학습 단계에서는 응답 바디 허용
- **비밀번호는 bcrypt 해시** — 절대 평문 저장·로그 금지
- **JWT secret 은 환경 변수**

## 응답 형식

### 단건 조회

```python
@router.get("/{user_id}", response_model=UserRead)
```

### 목록 조회 (페이지네이션)

```python
class Page(BaseModel):
    items: list[EventRead]
    total: int
    page: int
    size: int


@router.get("", response_model=Page[EventRead])
async def listEvents(
    page: int = 1,
    size: int = 20,
    session: AsyncSession = Depends(getCoreReaderSession),
) -> Page[EventRead]:
    items, total = await EventService(session).list(page=page, size=size)
    return Page(
        items=[EventRead.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
    )
```

### 규칙
- **목록은 항상 `Page` 래퍼 사용** — 단순 list 반환 금지 (총 개수 누락 방지)
- **page 1-based**, **size 기본 20 / 최대 100** — service 레이어에서 검증
- **정렬은 명시 파라미터로만** — 암묵적 기본 정렬 금지 (`created_at desc` 같이 명시)

## 페이지네이션 · 필터링 · 정렬

```python
@router.get("", response_model=Page[EventRead])
async def listEvents(
    page: int = 1,
    size: int = 20,
    venue: str | None = None,
    starts_after: datetime | None = None,
    sort: Literal["starts_at", "-starts_at", "created_at", "-created_at"] = "-starts_at",
    session: AsyncSession = Depends(getCoreReaderSession),
) -> Page[EventRead]:
    ...
```

### 규칙
- **필터는 query 파라미터로 명시** — 동적 `where` 문자열 받기 금지 (SQL injection·디버깅 난이도)
- **정렬은 화이트리스트** — `Literal[...]` 로 가능한 값 한정. 음수 prefix(`-`) = 내림차순
- **서버 측 검증** — 페이지/사이즈 범위, 정렬 가능 필드는 service 진입 직전 검증

## 라우터 → Service 호출 패턴

### 단순 조회

```python
@router.get("/{event_id}", response_model=EventRead)
async def getEvent(
    event_id: UUID,
    session: AsyncSession = Depends(getCoreReaderSession),
) -> EventRead:
    event = await EventService(session).getById(event_id)
    return EventRead.model_validate(event)
```

### 좌석 hold (인증 필요)

```python
@router.post("/holds", response_model=HoldRead, status_code=status.HTTP_201_CREATED)
async def holdSeat(
    payload: HoldCreate,
    user: User = Depends(getCurrentUser),
    redis = Depends(getRedisClient),
) -> HoldRead:
    hold_token = await ReservationService(redis=redis).hold(
        user_id=user.id, event_id=payload.event_id, seat_no=payload.seat_no,
    )
    return HoldRead(hold_token=hold_token)
```

### 예매 확정 (인증 필요)

```python
@router.post("/confirm", response_model=ReservationRead, status_code=status.HTTP_201_CREATED)
async def confirmReservation(
    payload: ConfirmCreate,
    user: User = Depends(getCurrentUser),
    redis = Depends(getRedisClient),
    res_writer: AsyncSession = Depends(getReservationWriterSession),
) -> ReservationRead:
    reservation = await ReservationService(
        reservation_writer=res_writer, redis=redis,
    ).confirm(
        user_id=user.id,
        hold_token=payload.hold_token,
        payment_method=payload.payment_method,
    )
    return ReservationRead.model_validate(reservation)
```

> **결제 PG 호출 없음** — `payment_method` 는 Mock 기록 용 문자열로만 보관. 외부 charge 호출 없음.

### 규칙
- **라우터 함수는 5 줄 내외** — 검증·service 호출·응답 변환 외 로직 금지
- **예외는 catch 하지 않는다** — service 가 던진 도메인 예외는 글로벌 핸들러에서 처리 (04-error-handling.md 참조)
- **로깅도 라우터에서 하지 않음** — request middleware 가 일괄 처리

## OpenAPI 메타데이터

### 엔드포인트 설명

```python
@router.post(
    "",
    response_model=ReservationRead,
    status_code=status.HTTP_201_CREATED,
    summary="좌석 예매 생성",
    responses={
        409: {"description": "이미 선점된 좌석"},
        404: {"description": "이벤트 없음"},
    },
)
async def createReservation(...) -> ReservationRead: ...
```

### 규칙
- **summary 는 한 줄 한국어** — 한국어 단일 정책 ([06-code-style.md](06-code-style.md))
- **에러 응답은 주요 도메인 예외만 명시** — 모든 상태 코드 나열 X
- **docstring 작성 금지** — summary 로 충분. router 함수 docstring 은 자동으로 OpenAPI description 이 되는데, summary 와 중복

## 미들웨어

### 필수 미들웨어
- **CORS** — 운영 도메인 화이트리스트만 허용
- **request_id 부여** — 모든 요청에 UUID 발급, structlog context 에 주입

```python
# app/main.py
import uuid

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

import structlog


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


app.add_middleware(RequestIdMiddleware)
```

> 인증·로깅·메트릭 미들웨어는 [04-error-handling.md](04-error-handling.md) 에 상세 정의.

## 안티 패턴

### 금지
- **라우터 안에서 SQLAlchemy 쿼리 직접 작성** — repository 통해서만
- **service 가 `HTTPException` 발생** — service 는 도메인 예외만, HTTP 변환은 글로벌 핸들러
- **응답에 ORM 객체 그대로 반환** — 반드시 `model_validate` 거치기 (보안: 의도치 않은 필드 노출 방지)
- **`@router.api_route` 로 여러 메서드 한 함수에 매핑** — 가독성 저하
- **dict 응답 (`return {"id": 1, ...}`)** — Pydantic 모델 미사용 시 OpenAPI 스펙 누락
- **글로벌 `@app.middleware("http")` 데코레이터 남용** — `add_middleware` 또는 `BaseHTTPMiddleware` 클래스 사용
