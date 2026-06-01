# 에러 처리 · 로깅 · 모니터링

## 핵심 원칙

> **간략화 우선** — 도메인 예외는 **실제로 발생 + 호출자가 분기하는 케이스만** 정의한다. "혹시 모르니" 예외 추가 금지. 5xx 일 가능성이 있는 모든 곳에 try/except 를 박지 않는다 — 글로벌 핸들러가 잡는다.

## 에러 처리 원칙

1. **fail-fast** — 검증 실패는 즉시 raise. 입력을 "보정" 하지 않는다
2. **도메인 예외 + 글로벌 핸들러** — service 는 도메인 예외만 raise, HTTP 변환은 한 곳에서
3. **상위로 위임** — 잡아서 처리할 수 없으면 잡지 않는다 (FastAPI 가 5xx 로 반환)
4. **컨텍스트 보존** — `raise X from e` 로 원인 체인 유지

## 도메인 예외 계층

### 베이스

```python
# app/common/errors.py
from typing import Any


class DomainError(Exception):
    """모든 도메인 예외의 베이스."""

    status_code: int = 500
    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
```

### 표준 예외 (실제 사용되는 것만 정의)

```python
# === Auth ===
class InvalidTokenError(DomainError):
    status_code = 401
    code = "INVALID_TOKEN"

    def __init__(self) -> None:
        super().__init__("유효하지 않은 토큰입니다")


class InvalidCredentialsError(DomainError):
    status_code = 401
    code = "INVALID_CREDENTIALS"

    def __init__(self) -> None:
        super().__init__("이메일 또는 비밀번호가 올바르지 않습니다")


# === User ===
class UserNotFoundError(DomainError):
    status_code = 404
    code = "USER_NOT_FOUND"

    def __init__(self, *, user_id: int) -> None:
        super().__init__("사용자를 찾을 수 없습니다", user_id=user_id)


class DuplicateEmailError(DomainError):
    status_code = 409
    code = "DUPLICATE_EMAIL"

    def __init__(self, *, email: str) -> None:
        super().__init__("이미 사용 중인 이메일입니다", email=email)


# === Event ===
class EventNotFoundError(DomainError):
    status_code = 404
    code = "EVENT_NOT_FOUND"

    def __init__(self, *, event_id: int) -> None:
        super().__init__("이벤트를 찾을 수 없습니다", event_id=event_id)


# === Reservation ===
class SeatAlreadyTakenError(DomainError):
    status_code = 409
    code = "SEAT_ALREADY_TAKEN"

    def __init__(self, *, event_id: int, seat_no: str | None = None) -> None:
        super().__init__("이미 선점된 좌석입니다", event_id=event_id, seat_no=seat_no)


class ReservationNotFoundError(DomainError):
    status_code = 404
    code = "RESERVATION_NOT_FOUND"

    def __init__(self, *, reservation_id: int) -> None:
        super().__init__("예매를 찾을 수 없습니다", reservation_id=reservation_id)


# === Payment ===
# Payment 도메인 예외는 정의하지 않는다 — 외부 PG 미연동이라 실패 경로가 없다
```

### 규칙
- **카테고리 enum·추상 클래스 트리 만들지 않는다** — 위 평면 구조로 충분
- **모든 예외는 `status_code` 와 `code` 를 클래스 변수로 명시** — HTTP 응답 일관성
- **메시지는 한국어** — 사용자 노출 가능
- **details 는 디버깅·로그용** — 민감 정보 (비밀번호 등) 금지

## 글로벌 예외 핸들러

```python
# app/main.py
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

from app.common.errors import DomainError

logger = structlog.get_logger()
app = FastAPI()


@app.exception_handler(DomainError)
async def domainErrorHandler(request: Request, exc: DomainError) -> JSONResponse:
    logger.warning(
        "domain_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(RequestValidationError)
async def validationErrorHandler(
    request: Request, exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message": "요청 검증 실패", "details": exc.errors()},
    )


@app.exception_handler(IntegrityError)
async def integrityErrorHandler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.error("integrity_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=409,
        content={"code": "CONFLICT", "message": "데이터 충돌이 발생했습니다"},
    )


@app.exception_handler(OperationalError)
async def operationalErrorHandler(request: Request, exc: OperationalError) -> JSONResponse:
    logger.error("db_operational_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=503,
        content={"code": "DB_UNAVAILABLE", "message": "일시적인 데이터베이스 오류"},
    )


@app.exception_handler(Exception)
async def unhandledErrorHandler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "예상치 못한 오류"},
    )
```

### 응답 표준 형식

```json
{
    "code": "SEAT_ALREADY_TAKEN",
    "message": "이미 선점된 좌석입니다",
    "details": {"event_id": 42, "seat_no": "A-12"}
}
```

- **모든 에러 응답은 위 3 필드** — 클라이언트가 단일 파서로 처리
- **`details` 는 디버깅·UX 보조** — 없으면 빈 객체

## 재시도 정책

### 정책 가이드

| 상황 | 재시도 | 이유 |
|---|---|---|
| DB `OperationalError` (커넥션 끊김, AZ failover) | 2 회, 짧은 backoff | RDS 페일오버 흡수 |
| DB `IntegrityError` (unique 충돌) | 재시도 안 함 | 비즈니스 결과 (좌석 선점됨) |
| Redis 일시 오류 | 1 회 | ElastiCache 커넥션 슬립 |
| SQS publish 실패 | 3 회, 지수 백오프 | 일시적 throttling |
| Lambda 처리 실패 | SQS visibility timeout 만큼 재처리 → DLQ | SQS 재시도 기본 동작 |

> 외부 HTTP API 호출이 없으므로 (결제 PG 미연동) 별도 retry 라이브러리 (`tenacity`) 도입 안 함. 위 정책은 라이브러리 없이 SQLAlchemy `pool_pre_ping`, redis-py 기본 재시도, SQS 자체 재시도로 처리.

### 규칙
- **재시도는 인프라 레이어가** — SQLAlchemy `pool_pre_ping`, SQS 재시도, k8s probe 재시작
- **애플리케이션 코드는 재시도 X** — 503 반환 후 클라이언트가 재시도하도록 위임 (백프레셔 — [09-traffic-and-scaling.md](09-traffic-and-scaling.md))

## 구조화 로깅 (structlog)

### 설정

```python
# app/common/logging.py
import logging
import sys

import structlog


def configureLogging(*, env: str = "development") -> None:
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
    ]

    if env == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
```

### 사용

```python
import structlog

logger = structlog.get_logger()

# 좋음 — 구조화 필드
logger.info(
    "reservation_created",
    user_id=user.id,
    event_id=event.id,
    seat_no=seat_no,
)

# 좋음 — 예외와 함께
logger.error(
    "payment_failed",
    reservation_id=reservation_id,
    error_code=exc.code,
    exc_info=True,
)

# 나쁨 — f-string
logger.info(f"사용자 {user.id} 가 예매 생성")
```

### 로그 레벨

| Level | 사용 시점 |
|---|---|
| **DEBUG** | 개발·트러블슈팅 시에만 필요한 상세 — 쿼리, 외부 호출 페이로드 |
| **INFO** | 운영자가 보고 싶은 정상 이벤트 — 가입, 로그인, 예매 생성, 결제 완료 |
| **WARN** | 예상 외이지만 처리됨 — 재시도, 도메인 예외 (4xx) |
| **ERROR** | 작업 실패 — 5xx, 외부 시스템 장애 |
| **CRITICAL** | 프로세스 종료 직전 — 거의 사용 안 함 |

### 메시지 명명 규칙
- **이벤트 이름은 snake_case 동사형 또는 명사형** — `reservation_created`, `payment_failed`, `db_connection_error`
- **메시지에 값 보간 금지** — 값은 필드로 전달
- **한국어 단일** — 다만 이벤트 이름은 ASCII (검색·집계 편의)

### 표준 필드

| 키 | 타입 | 설명 |
|---|---|---|
| `request_id` | str | 요청 단위 UUID (middleware 가 자동 주입) |
| `user_id` | int | 인증된 사용자 ID |
| `event_id` | int | Event ID |
| `reservation_id` | int | Reservation ID |
| `payment_id` | int | PaymentHistory ID |
| `error_code` | str | 도메인 예외 코드 (`SEAT_ALREADY_TAKEN` 등) |
| `status_code` | int | HTTP 응답 코드 |
| `duration_ms` | int | 처리 시간 (ms) |
| `path` | str | 요청 경로 |
| `method` | str | HTTP 메서드 |

### request_id 전파

```python
# app/main.py
import structlog
import uuid

from starlette.middleware.base import BaseHTTPMiddleware


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
```

### 보안
- **민감 정보 로깅 금지** — 비밀번호, JWT raw, 결제 카드 번호
- **PII 마스킹** — 이메일 도메인만 (`***@example.com`), 전화번호 끝 4자리만

## 모니터링 — CloudWatch (단일 스택)

본 시스템은 **CloudWatch 만** 사용한다. Prometheus·Datadog 등 별도 모니터링 스택 도입 안 함.

### 역할

| 컴포넌트 | 용도 |
|---|---|
| **CloudWatch Logs** | EKS Pod stdout (structlog JSON) → Fluent Bit → CloudWatch Logs Insights 검색 |
| **CloudWatch Metrics** | AWS 리소스 기본 metric (ALB · RDS · ElastiCache · SQS · Lambda · EKS) — **커스텀 metric 사용 안 함** |
| **CloudWatch Alarms** | 임계치 알람 → SNS → Slack |

### 애플리케이션은 stdout 만 신경 쓴다

```python
# 좋음 — JSON 한 줄. Fluent Bit 가 CloudWatch Logs 로 전달
logger.info("reservation_created", user_id=str(user_id), event_id=str(event_id))
```

CloudWatch Logs Insights 쿼리로 카운트·집계 가능:

```
fields @timestamp, user_id, event_id
| filter event = "reservation_created"
| stats count() by event_id
```

### 비즈니스 메트릭이 필요한 경우
- **먼저 Logs Insights 쿼리로 대신**할 수 있는지 검토
- 그래도 필요하면 본 룰셋을 갱신하고 EMF (Embedded Metric Format) 또는 `PutMetricData` 도입
- 현재 단계에서는 도입 안 함

### AWS 기본 메트릭으로 충분한 항목

| 관심사 | CloudWatch metric |
|---|---|
| 요청 수 | `AWS/ApplicationELB`: `RequestCount` |
| 5xx 비율 | `AWS/ApplicationELB`: `HTTPCode_Target_5XX_Count` |
| 응답 지연 | `AWS/ApplicationELB`: `TargetResponseTime` |
| EKS Pod 수 | `AWS/EKS` + Container Insights |
| RDS CPU·커넥션 | `AWS/RDS`: `CPUUtilization`, `DatabaseConnections` |
| Redis hit/miss | `AWS/ElastiCache`: `CacheHits`, `CacheMisses` |
| SQS 적체 | `AWS/SQS`: `ApproximateNumberOfMessagesVisible` |
| Lambda 실행 | `AWS/Lambda`: `Invocations`, `Errors`, `Duration` |

> 비즈니스 지표 (예매 건수 등) 가 정말 필요해지면 CloudWatch Logs Insights 쿼리로 먼저 처리한다.

## 헬스체크 (k8s probe + ALB target)

EKS 의 liveness/readiness probe 와 ALB target health 가 모두 본 엔드포인트를 호출한다.

```python
# app/routers/health.py
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.deps import (
    getCoreReaderSession,
    getReservationReaderSession,
    getRedisClient,
)

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(
    core: AsyncSession = Depends(getCoreReaderSession),
    reservation: AsyncSession = Depends(getReservationReaderSession),
    redis = Depends(getRedisClient),
) -> dict[str, str]:
    await core.execute(text("SELECT 1"))
    await reservation.execute(text("SELECT 1"))
    await redis.ping()
    return {"status": "ready"}
```

### 규칙
- **`/healthz`** (liveness) — 프로세스 살아있는지만. 외부 의존성 검사 X
  - k8s `livenessProbe` 와 ALB target health 둘 다 가능
  - DB 다운 시 readiness 만 fail 시키고 liveness 는 유지 (불필요한 재시작 회피)
- **`/readyz`** (readiness) — DB · Redis 의존성 검사
  - 의존성 fail 시 503 반환 → ALB 가 트래픽 차단, 다른 정상 Pod 로 라우팅
- **인증 면제** — 둘 다 공개 엔드포인트
- **HTTP 응답 코드** — readiness 실패는 503 (`HTTPException(status_code=503)`)

### 그레이스풀 셧다운

k8s rolling update 시 SIGTERM → preStop hook → 신규 트래픽 차단 → in-flight 요청 완료 → 종료.

```python
# app/main.py
from contextlib import asynccontextmanager
import asyncio
import signal

shutting_down = False

@asynccontextmanager
async def lifespan(app):
    # startup
    yield
    # shutdown — uvicorn 이 자동으로 in-flight 처리 후 종료
    # 추가로 redis/aioboto3 client 명시 close


# readiness 가 셧다운 중에는 503 반환 → ALB 가 트래픽 끊음
@router.get("/readyz")
async def readiness(...) -> dict[str, str]:
    if shutting_down:
        raise HTTPException(status_code=503, detail="shutting down")
    ...
```

> uvicorn 의 `--timeout-graceful-shutdown` 옵션과 k8s `terminationGracePeriodSeconds` 를 맞춘다 (30s 권장).

## 알림 규칙 (CloudWatch Alarms)

CloudWatch Alarm 으로 정의하고 SNS → Slack 라우팅. Terraform 으로 IaC 관리 ([08-aws-infrastructure.md](08-aws-infrastructure.md)).

AWS 기본 metric 기반 알람만 정의한다 — 인프라 검증에 필요한 최소 셋.

| Alarm 이름 | 조건 | 심각도 |
|---|---|---|
| `ALB5xxHigh` | ALB `HTTPCode_Target_5XX_Count` 5분 합계 > 50 | warning |
| `ALBTargetUnhealthy` | `UnHealthyHostCount` > 0 (5분) | warning |
| `RDSWriterCPUHigh` | `CPUUtilization` (writer) > 80% (10분) | warning |
| `RDSReadReplicaLag` | `ReplicaLag` > 5s (5분) | warning |
| `SQSDLQDepth` | `ApproximateNumberOfMessagesVisible` (DLQ) > 0 | critical |
| `LambdaErrorRate` | `Errors / Invocations` > 5% (5분) | warning |

## 인시던트 대응

### 운영자 액션 순서
1. **request_id 또는 user_id 로 로그 추적** — structlog JSON 검색
2. **메트릭 대시보드 확인** — 영향 범위 (어떤 엔드포인트·도메인)
3. **재시도/스로틀 조치** — 외부 시스템 장애면 결제 등 일시 차단
4. **포스트모템 작성** — 원인·영향·재발 방지

### 데이터 정합성 점검
- **두 RDS 간 비대칭 의심** — `event.available_seats` 와 실제 `reservation` 수 비교
- **결제 미완료 예매** — `reservation.status = confirmed` + `payment.status = failed/pending` 케이스 주기적 검사

## 안티 패턴

### 금지
- **모든 예외를 `except Exception` 으로 잡아 5xx 반환** — 글로벌 핸들러가 함. 코드 어지럽힘
- **service 안에서 `HTTPException` raise** — 도메인 예외만
- **로그 메시지에 f-string + 값 보간** — 구조화 필드로
- **`print()` 디버깅 잔존** — ruff `T201` 룰로 차단
- **예외 발생 시 `pass` 또는 `... # ignore`** — 의도가 있으면 주석 한 줄로 *왜* 무시하는지 명시
- **재시도 없이 외부 호출** + **무한 재시도** 둘 다 금지 — 명시적 횟수·백오프
- **민감 정보 로그** — 비밀번호, JWT, 카드 번호 절대 금지
