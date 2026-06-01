# 테스트 전략 및 품질 게이트

## 핵심 원칙

> **간략화 우선** — 모든 함수에 단위 테스트를 강제하지 않는다. **핵심 비즈니스 경로 + 회귀 위험 지점**을 우선 커버한다. 테스트 자체에도 안티 패턴이 있다: 과한 mock·과한 분기·과한 setup 은 유지보수성을 떨어뜨린다.

## 테스트 철학

### 커버리지 목표

| 영역 | 목표 |
|---|---|
| 전체 코드 | 70%+ |
| `domains/<name>/service.py` (핵심 로직) | 90%+ |
| `routers/` (인증·검증 경로) | 80%+ |
| `common/security.py` (JWT, 해시) | 95%+ |
| repository | 60%+ (CRUD 정상 경로) |
| model | 단순 매핑은 강제 X |

### 테스트 피라미드

```
   E2E (5%)    ← 라우터 + 실제 DB 통합
  ┌───────────┐
  │Integration│ (25%)  ← service + 실제 DB / TestClient + mocked PG
  ├───────────┤
  │   Unit    │ (70%)  ← service 비즈니스 로직, 도메인 메서드, 헬퍼
  └───────────┘
```

### 원칙
1. **테스트는 격리된다** — 다른 테스트의 상태에 의존하지 않음
2. **테스트는 결정적이다** — `datetime.now()` 같은 비결정 요소 freeze
3. **외부 의존성은 mock 또는 컨테이너** — 실제 PG 호출 금지
4. **느린 테스트는 마킹** — `@pytest.mark.slow` 로 분리 실행 가능

## 디렉토리 구조 (소스 미러링)

```
tests/
├── conftest.py                  # 전역 fixture
├── common/
│   ├── test_security.py         # JWT, 비밀번호 해시
│   └── test_errors.py
├── domains/
│   ├── user/
│   │   ├── test_repository.py
│   │   ├── test_service.py
│   │   └── test_model.py
│   ├── event/
│   ├── reservation/
│   │   ├── test_repository.py
│   │   └── test_service.py      # 핵심: 예매 동시성
│   └── payment/
└── routers/
    ├── test_auth.py             # 라우터 + DB 통합
    ├── test_events.py
    └── test_reservations.py
```

### 규칙
- **소스 디렉토리와 동일 구조** — `app/domains/user/service.py` → `tests/domains/user/test_service.py`
- **테스트 파일은 `test_*.py`**, 함수는 `test_*`
- **테스트 클래스 사용 자제** — pytest 함수 스타일로 충분. 픽스처 공유가 필요할 때만 클래스

## 테스트 네이밍

### 패턴
```
test_<함수명>_<시나리오>_<기대결과>
```

### 예시

```python
def test_create_reservation_with_available_seat_succeeds(): ...
def test_create_reservation_when_seat_taken_raises_seat_taken_error(): ...
def test_create_reservation_when_event_not_found_raises_event_not_found(): ...
def test_authenticate_with_wrong_password_raises_invalid_credentials(): ...
```

### 규칙
- **영어 ASCII** — 검색·CI 출력 가독성
- **한글 함수명 사용 안 함** — pytest 자체는 지원하지만 디버거·CI 화면에서 깨짐 위험
- **시나리오·기대결과 모두 명시** — `test_create_reservation_works` 같은 모호한 이름 금지

## 픽스처

### 전역 fixture (`tests/conftest.py`)

```python
# tests/conftest.py
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.common.db import CoreBase, ReservationBase
from app.main import app


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def coreEngine() -> AsyncIterator:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def reservationEngine() -> AsyncIterator:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ReservationBase.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def coreSession(coreEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(coreEngine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def reservationSession(reservationEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(reservationEngine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def redis() -> AsyncIterator:
    """fakeredis 또는 testcontainers 의 redis. 테스트 단위 격리."""
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client(coreSession, reservationSession, redis) -> AsyncIterator[AsyncClient]:
    # 단위 테스트에서는 writer/reader 가 같은 세션을 가리키도록 단순화
    from app.common.deps import (
        getCoreWriterSession, getCoreReaderSession,
        getReservationWriterSession, getReservationReaderSession,
        getRedisClient,
    )

    async def overrideCore(): yield coreSession
    async def overrideReservation(): yield reservationSession
    async def overrideRedis(): return redis

    app.dependency_overrides[getCoreWriterSession] = overrideCore
    app.dependency_overrides[getCoreReaderSession] = overrideCore
    app.dependency_overrides[getReservationWriterSession] = overrideReservation
    app.dependency_overrides[getReservationReaderSession] = overrideReservation
    app.dependency_overrides[getRedisClient] = overrideRedis

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
```

> 테스트에서는 writer/reader 분리 효과를 검증하지 않고, **동작** 만 확인한다. writer/reader endpoint 자체 (replication lag 등) 검증은 staging 에서 Locust 로 수행.

### 도메인 픽스처 — 빌더 패턴 (간단히)

```python
# tests/domains/event/conftest.py
import pytest_asyncio

from app.domains.event.model import Event


@pytest_asyncio.fixture
async def existingEvent(coreSession) -> Event:
    event = Event(
        title="테스트 콘서트",
        venue="잠실",
        starts_at=datetime(2026, 12, 31, 19, 0, tzinfo=timezone.utc),
        total_seats=100,
        available_seats=100,
    )
    coreSession.add(event)
    await coreSession.flush()
    return event
```

### 규칙
- **픽스처는 가까운 conftest.py 에** — `tests/conftest.py` 전역, `tests/domains/event/conftest.py` 도메인 한정
- **fixture 이름은 camelCase** — 메서드 네이밍 컨벤션 일관
- **factory_boy 같은 라이브러리 도입 X** — 직접 객체 생성 헬퍼로 충분 (간략화)
- **DB 격리** — 함수 단위 fixture 로 매 테스트 fresh schema, 또는 transaction rollback 패턴

## 단위 테스트 — service

### 예시: 좌석 hold 성공

```python
# tests/domains/reservation/test_service.py
import pytest

from app.domains.reservation.service import ReservationService


@pytest.mark.asyncio
async def test_hold_seat_succeeds(redis, existingEvent, authUser):
    service = ReservationService(redis=redis)

    hold_token = await service.hold(
        user_id=authUser.id, event_id=existingEvent.id, seat_no="A-1",
    )

    assert hold_token
    assert await redis.get(f"seat:hold:{existingEvent.id}:A-1") is not None
```

### 예시: 동시성 — 이미 hold 된 좌석은 실패

```python
@pytest.mark.asyncio
async def test_hold_when_already_held_raises(redis, existingEvent, authUser):
    service = ReservationService(redis=redis)
    await service.hold(user_id=authUser.id, event_id=existingEvent.id, seat_no="A-1")

    with pytest.raises(SeatAlreadyTakenError) as exc:
        await service.hold(user_id=authUser.id, event_id=existingEvent.id, seat_no="A-1")
    assert exc.value.details["event_id"] == existingEvent.id
```

### 예시: 확정 시 payment_history mock 기록

```python
@pytest.mark.asyncio
async def test_confirm_records_payment_history(
    redis, reservationWriterSession, existingEvent, authUser,
):
    service = ReservationService(
        reservation_writer=reservationWriterSession, redis=redis,
    )
    hold_token = await service.hold(
        user_id=authUser.id, event_id=existingEvent.id, seat_no="A-1",
    )

    reservation = await service.confirm(
        user_id=authUser.id, hold_token=hold_token, payment_method="mock",
    )

    assert reservation.is_canceled is False
    # payment_history 가 같은 트랜잭션에서 기록됐는지 확인
    histories = await PaymentRepository(reservationWriterSession).listByReservation(reservation.id)
    assert len(histories) == 1
    assert histories[0].payment_method == "mock"
```

### 규칙
- **AAA 패턴**: Arrange → Act → Assert. 명시적 빈 줄로 분리
- **`pytest.raises` 로 예외 검증** — 메시지가 아니라 예외 타입과 details
- **assert 는 의미 있는 것만** — 모든 필드 비교 X. 핵심 결과만
- **외부 PG mock 불필요** — 본 시스템엔 외부 결제 호출이 없음. Payment 테스트는 단순 DB 기록 검증만

## 테이블 기반 테스트 (parametrize)

```python
import pytest


@pytest.mark.parametrize(
    "email, password, expected_error",
    [
        ("", "valid_pw_1234", "VALIDATION_ERROR"),
        ("not-email", "valid_pw_1234", "VALIDATION_ERROR"),
        ("user@example.com", "", "VALIDATION_ERROR"),
        ("user@example.com", "short", "VALIDATION_ERROR"),
    ],
)
@pytest.mark.asyncio
async def test_signup_with_invalid_input_returns_422(
    client, email: str, password: str, expected_error: str,
):
    response = await client.post("/users/signup", json={"email": email, "password": password})
    assert response.status_code == 422
    assert response.json()["code"] == expected_error
```

## 통합 테스트 — 라우터 + DB

### TestClient 패턴

```python
# tests/routers/test_reservations.py
import pytest


@pytest.mark.asyncio
async def test_post_reservations_returns_201(client, existingEvent, authHeaders):
    response = await client.post(
        "/reservations",
        json={"event_id": existingEvent.id, "seat_no": "A-1"},
        headers=authHeaders,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["seat_no"] == "A-1"


@pytest.mark.asyncio
async def test_post_reservations_without_token_returns_401(client, existingEvent):
    response = await client.post(
        "/reservations",
        json={"event_id": existingEvent.id, "seat_no": "A-1"},
    )
    assert response.status_code == 401
```

### 인증 fixture

```python
# tests/conftest.py
@pytest_asyncio.fixture
async def authUser(coreSession):
    from app.common.security import hashPassword
    from app.domains.user.model import User

    user = User(email="tester@example.com", password_hash=hashPassword("password1234"))
    coreSession.add(user)
    await coreSession.flush()
    return user


@pytest.fixture
def authHeaders(authUser) -> dict[str, str]:
    from app.common.security import issueAccessToken
    token = issueAccessToken(authUser.id)
    return {"Authorization": f"Bearer {token}"}
```

## DB 통합 — testcontainers (선택적)

운영과 동일한 PostgreSQL 동작 검증이 필요할 때만 사용. 대부분의 단위 테스트는 SQLite 로 충분.

```python
@pytest_asyncio.fixture(scope="session")
async def postgresContainer():
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:16-alpine")
    container.start()
    yield container.get_connection_url()
    container.stop()
```

### 규칙
- **session scope** — 컨테이너 1회 부팅, 테스트 간 truncate
- **`@pytest.mark.slow` 부여** — 빠른 CI 단계에서 제외 가능
- **PostgreSQL 고유 기능 (`FOR UPDATE`, `ON CONFLICT`) 검증 시에만**

## 모킹 정책

### Mock 대상
- **외부 HTTP 호출** (결제 PG) — `unittest.mock.AsyncMock`
- **시간** — `freezegun` 또는 `time-machine`
- **랜덤** — `monkeypatch` 로 시드 고정

### Mock 금지
- **자기 도메인의 repository** — 가능하면 실제 DB 사용. mock 하면 SQL 버그를 못 잡음
- **Pydantic schema** — 그냥 객체 만들면 됨

### 좋은 mock 예시

```python
@pytest.mark.asyncio
async def test_payment_handles_pg_5xx_with_retry(reservationSession):
    mock_pg = AsyncMock()
    mock_pg.charge.side_effect = [
        httpx.HTTPStatusError("503", request=..., response=...),
        ChargeResult(success=True, transaction_id="tx-1"),
    ]
    service = PaymentService(reservationSession, mock_pg)
    result = await service.charge(reservation_id=1, amount=10000)
    assert result.status == "completed"
    assert mock_pg.charge.await_count == 2
```

## 비동기 코드 테스트

### 규칙
- **모든 async 테스트에 `@pytest.mark.asyncio`** — pytest-asyncio 의 `asyncio_mode = "strict"` 설정 권장
- **`AsyncClient` 사용** — `TestClient` 는 동기. async 라우터 디버깅 어려움
- **`async with`** 컨텍스트 매니저로 리소스 정리

### pyproject.toml 설정

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-ra --strict-markers --strict-config"
markers = [
    "slow: 느린 테스트 (testcontainers 등)",
]
```

`asyncio_mode = "auto"` 면 데코레이터 생략 가능. 명시 선호 시 `strict`.

## 동시성 테스트

좌석 예매 race condition 검증.

```python
import asyncio

@pytest.mark.asyncio
async def test_concurrent_reservation_only_one_succeeds(
    coreSession, reservationSession, existingEvent,
):
    # 좌석 1석만 남은 이벤트
    existingEvent.available_seats = 1
    await coreSession.flush()

    service = ReservationService(reservationSession, coreSession)
    payload = ReservationCreate(event_id=existingEvent.id, seat_no="A-1")

    results = await asyncio.gather(
        service.create(user_id=1, payload=payload),
        service.create(user_id=2, payload=payload),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, SeatAlreadyTakenError)]
    assert len(successes) == 1
    assert len(failures) == 1
```

> SQLite in-memory 는 동시성 시뮬레이션이 제한적 → 실제 race 검증은 testcontainers PostgreSQL 권장.

## 품질 게이트

### Pre-commit (선택)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, sqlalchemy]
```

### 커버리지 측정

```bash
pytest --cov=app --cov-report=term-missing --cov-report=html

# 최소 커버리지 강제
pytest --cov=app --cov-fail-under=70
```

### 커버리지 제외

```python
# pyproject.toml
[tool.coverage.run]
omit = [
    "app/main.py",      # 부팅 코드
    "app/settings.py",  # 환경 설정만
    "*/migrations/*",
]
```

## CI 워크플로우

```yaml
# .github/workflows/test.yml
name: tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: 의존성 설치
        run: |
          pip install -e ".[dev]"

      - name: lint
        run: |
          ruff check .
          ruff format --check .

      - name: 타입 검사
        run: mypy app

      - name: 테스트 + 커버리지
        run: pytest --cov=app --cov-report=xml --cov-fail-under=70

      - name: 커버리지 업로드
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
```

## 안티 패턴

### 금지
- **`time.sleep()` 으로 비동기 결과 기다리기** — `await` 또는 `asyncio.wait_for`
- **mock 으로 모든 의존성 가짜 처리** — 실제 코드 경로가 안 돌아가서 회귀 못 잡음
- **assert 100 줄 짜리 god test** — 한 테스트는 한 가지만
- **fixture 안에서 비즈니스 로직 실행** — fixture 는 상태 준비만
- **테스트 코드에 if/else 분기** — `parametrize` 로 분기 분해
- **테스트 간 공유 상태** (`module` scope DB 등) — 격리 깨짐
- **commit 안 한 테스트 코드** — `pytest.mark.skip("작업 중")` 으로 일단 마킹 후 push
