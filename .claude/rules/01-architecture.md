# 아키텍처 및 디렉토리 구조

## 핵심 원칙

> **간략화 우선** — 본 문서의 모든 구조는 학습·실습 규모의 티켓팅 서비스에 맞춰 **최소한**으로 정의된다. 엔터프라이즈 패턴(UseCase·CQRS·Hexagonal·Event Sourcing 등)을 임의로 도입하지 않는다. 새 레이어가 필요해 보이면 먼저 [README.md 의 "간략화 원칙"](README.md#프로젝트-성격--간략화-원칙-필독) 을 다시 읽는다.

## 시스템 개요

- **프로젝트**: 티켓팅 서비스 (팀 C.C — Cloud Crusade)
- **부제**: 고가용성 클라우드 인프라 및 모니터링 시스템
- **목적**: **AWS 인프라 (EKS·RDS·ElastiCache·SQS·CloudWatch) 의 스파이크 흡수 능력 검증**
- **기능 범위**: 인증 + 행사 관리 + 티켓팅 — 그 외 기능 없음 (자세한 범위는 [README.md](README.md))
- **엔티티 4개**: User · Event · Reservation · PaymentHistory (PaymentHistory 는 mock 기록만)
- **인증**: JWT (access + refresh)
- **운영 환경**: AWS · 분산 처리 (다중 EKS Pod + Multi-AZ RDS + ElastiCache + SQS+Lambda)

### 비즈니스 특성 (검증 시나리오)
- **평시**: 트래픽 매우 낮음 → 비용 최적화 위해 최소 인스턴스
- **티켓 오픈**: 수만 RPS 스파이크 → EKS HPA 로 Pod 스케일 아웃 + 좌석 hold + 백프레셔
- **고가용성**: Multi-AZ DB · ALB · EKS
- **모니터링**: CloudWatch (실시간 리소스·요청 지연 추적)

## 아키텍처 레이어 (애플리케이션 내부)

```
┌──────────────────────────────────────────┐
│  Routers (FastAPI APIRouter)             │  ← HTTP 입출력, 인증·검증
├──────────────────────────────────────────┤
│  Services (도메인별)                       │  ← 비즈니스 로직, 트랜잭션 경계
├──────────────────────────────────────────┤
│  Repositories (도메인별)                   │  ← SQLAlchemy 쿼리만
├──────────────────────────────────────────┤
│  Models (SQLAlchemy ORM)                  │  ← 테이블 매핑 + 도메인 메서드
├──────────────────────────────────────────┤
│  RDS #1 (User/Event)   RDS #2 (Reservation/Payment)
└──────────────────────────────────────────┘
```

## 인프라 토폴로지 (AWS)

본 시스템은 AWS 위에서 동작하며, [Notion 의 아키텍처 다이어그램](https://www.notion.so/36de8b70b7aa80f59e54d08bb5c96b06) 을 단일 출처로 삼는다.

```
                              ┌────────────────┐
                              │   CloudWatch   │  ← 모든 컴포넌트 metric/log
                              └────────────────┘
                                      ▲
   Infra GitHub  ──► S3 (tf state)    │
   Service GitHub ──► ECR (image)     │
                                      │
                          Region (ap-northeast-2)
                          ┌──────────────────────────────────────────────┐
                          │                  VPC                          │
                          │ ┌─────────────────┐                           │
                          │ │  Public subnet  │                           │
                          │ │  ALB + ACM      │     Bastion               │
                          │ │  EventBridge    │                           │
                          │ └────────┬────────┘                           │
                          │          │                                    │
                          │ ┌────────▼──────────────────────────────────┐ │
                          │ │  Private subnet  (Availability Zone #1)   │ │
                          │ │  ┌──────────┐   ┌──────────────────┐      │ │
                          │ │  │  EKS Pod │   │  RDS writer       │     │ │
                          │ │  │  EKS Pod │──►│  RDS readonly     │     │ │
                          │ │  └──────────┘   └──────────────────┘      │ │
                          │ └───────────────────────────────────────────┘ │
                          │ ┌───────────────────────────────────────────┐ │
                          │ │  Private subnet  (Availability Zone #2)   │ │
                          │ │  ┌──────────┐   ┌──────────────────┐      │ │
                          │ │  │  EKS Pod │   │  RDS writer (rep) │     │ │
                          │ │  │  EKS Pod │──►│  RDS readonly     │     │ │
                          │ │  └──────────┘   └──────────────────┘      │ │
                          │ └───────────────────────────────────────────┘ │
                          │ ┌───────────────────────────────────────────┐ │
                          │ │  ElastiCache (Redis)  → 좌석 hold/idempotency│
                          │ │  SQS → Lambda (대기열, 세션 누수 방지)         │
                          │ └───────────────────────────────────────────┘ │
                          └──────────────────────────────────────────────┘
```

> 자세한 인프라 구성·Terraform 작성 가이드는 [08-aws-infrastructure.md](08-aws-infrastructure.md), 스파이크 대응·대기열·HPA 정책은 [09-traffic-and-scaling.md](09-traffic-and-scaling.md) 참조.

### 컴포넌트 책임

| 컴포넌트 | 역할 |
|---|---|
| **ALB + ACM** | TLS 종료, 다중 AZ 라우팅, 헬스체크 |
| **EKS Pod (FastAPI)** | API 처리. AZ 별 분산 배치. HPA 로 스파이크 시 스케일 아웃 |
| **RDS (writer)** | 트랜잭션 (write/update). AZ #1 마스터, AZ #2 stand-by 복제 |
| **RDS (reader)** | 읽기 전용 쿼리. 부하 분산. eventual consistency |
| **ElastiCache (Redis)** | 좌석 점유 분산 락 (`seat:hold:{event_id}:{seat_no}` TTL 5분) |
| **SQS** | 만료 hold 자동 release 큐 1개 (`seat-release`) + DLQ |
| **Lambda** | `seat-release` 컨슈머 (DB 좌석 잔여 복구 · 정합성 보정) |
| **EventBridge** | 정기 스케줄 (5분마다 stale hold 정리 트리거) |
| **CloudWatch** | 메트릭·로그·알람 집계 |
| **Bastion** | 운영자 SSH 접근 점 (Private subnet 진입) |
| **S3** | Terraform state 백엔드 + 정적 자산 |
| **ECR** | 서비스 컨테이너 이미지 레지스트리 |

### 레이어별 책임

| 레이어 | 책임 | 금지 |
|---|---|---|
| Router | 요청 파싱 · 인증 · service 호출 · 응답 형식 | 직접 SQL, 트랜잭션 시작, 비즈니스 분기 |
| Service | 비즈니스 규칙 · 트랜잭션 · 도메인 예외 발생 | HTTP 객체 의존, 응답 포맷 결정 |
| Repository | 쿼리 · INSERT/UPDATE/DELETE | 비즈니스 검증, 다른 도메인 호출 |
| Model | 테이블 매핑 · 상태 메서드 (예: `hasAvailableSeats()`) | 세션 직접 사용, repository 호출 |

### 의존성 방향
- 단방향: `router → service → repository → model`
- 역방향 import 금지 (model 이 service 를 부르면 즉시 잘못된 설계)
- 도메인 간 호출은 service 레이어에서만 (`ReservationService` 가 `EventRepository` 를 주입받아 사용)

## 다중 RDS 정책

본 시스템은 **두 개의 RDS 인스턴스 + 각 RDS 내 writer/reader 분리** 를 사용한다.

| RDS | 도메인 | 엔드포인트 | 이유 |
|---|---|---|---|
| **RDS #1 (core)** | User, Event | writer + reader | 읽기 트래픽 위주, 캐시 친화적 |
| **RDS #2 (reservation)** | Reservation, PaymentHistory | writer + reader | 쓰기 부하 · 락 경합 · 정합성 요구 분리 |

각 RDS 는 **Multi-AZ 복제** (AZ #1 마스터, AZ #2 stand-by) 구성으로 가용성 확보.

### 규칙
- **Cross-DB JOIN 금지** — DB 가 다르면 SQL JOIN 불가. service 레이어에서 ID 기반 조회 후 메모리 조합
- **단일 트랜잭션은 단일 DB 내** — `Reservation` 생성 트랜잭션 안에서 `User` 테이블 변경 금지. 2PC 도입 X
- **세션·엔진 분리** — `getCoreWriterSession`, `getCoreReaderSession`, `getReservationWriterSession`, `getReservationReaderSession` 4 종 의존성으로 분리
- **읽기는 reader 우선** — 단순 조회는 reader endpoint. 쓰기 직후 즉시 읽어야 하면 writer (replication lag 회피)
- **마이그레이션 분리** — Alembic 환경을 DB 별로 두 개 운영 (`alembic/core/`, `alembic/reservation/`)
- **failover 가정** — writer 가 AZ 페일오버 중 잠시 사용 불가할 수 있다. 재시도 정책 ([04-error-handling.md](04-error-handling.md)) 적용

> 세부 RDS 사용 패턴은 [03-domain-and-data.md](03-domain-and-data.md), 인프라 구성·Terraform 은 [08-aws-infrastructure.md](08-aws-infrastructure.md) 참조.

## 분산 환경 전제

- **상태는 외부 저장소에만 보관** — 프로세스 메모리 캐시·전역 dict 에 비즈니스 상태 보관 금지 (EKS Pod 가 다수 + 수시 재시작)
- **동시성 제어는 DB row lock 또는 Redis 분산 lock** — `asyncio.Lock` 으로 좌석 점유 같은 비즈니스 락 구현 금지
- **idempotency 보장** — 예매·결제 핵심 경로는 클라이언트 재시도 안전. idempotency_key 헤더 + Redis 저장
- **stateless API** — 세션 stickiness 가정 금지. JWT 자체로 인증 완결
- **그레이스풀 셧다운** — SIGTERM 수신 시 in-flight 요청 완료 후 종료 (k8s rolling update 안전)
- **k8s probe 응답** — liveness/readiness probe 에 의존성 검사 포함 ([04-error-handling.md](04-error-handling.md))

## 디렉토리 구조

```
app/
├── main.py                       # FastAPI 인스턴스, 라우터 등록, 예외 핸들러
├── settings.py                   # Pydantic Settings (환경 변수 로드)
│
├── common/                       # 공용 모듈 (도메인 무관)
│   ├── __init__.py
│   ├── deps.py                   # 의존성 (DB 세션, 현재 사용자)
│   ├── errors.py                 # DomainError 계층
│   ├── logging.py                # structlog 설정
│   ├── security.py               # JWT 인코딩/디코딩, 비밀번호 해싱
│   └── db.py                     # 두 RDS 엔진/세션 팩토리
│
├── domains/                      # 도메인별 모듈 (모듈형 DDD)
│   ├── user/
│   │   ├── __init__.py
│   │   ├── model.py              # SQLAlchemy User 모델 (RDS #1)
│   │   ├── schema.py             # Pydantic 스키마 (UserCreate, UserRead, ...)
│   │   ├── repository.py         # UserRepository
│   │   └── service.py            # UserService
│   ├── event/
│   │   ├── model.py              # Event 모델 (RDS #1)
│   │   ├── schema.py
│   │   ├── repository.py
│   │   └── service.py
│   ├── reservation/
│   │   ├── model.py              # Reservation 모델 (RDS #2)
│   │   ├── schema.py
│   │   ├── repository.py
│   │   └── service.py
│   └── payment/
│       ├── model.py              # PaymentHistory 모델 (RDS #2)
│       ├── schema.py
│       ├── repository.py
│       └── service.py
│
├── routers/                      # API 라우터 (controller)
│   ├── __init__.py
│   ├── auth.py                   # /auth/login, /auth/refresh
│   ├── users.py                  # /users
│   ├── events.py                 # /events
│   ├── reservations.py           # /reservations
│   └── payments.py               # /payments
│
└── alembic/                      # 마이그레이션 (DB 별 분리)
    ├── core/                     # RDS #1: user, event
    │   ├── env.py
    │   └── versions/
    └── reservation/              # RDS #2: reservation, payment_history
        ├── env.py
        └── versions/

tests/                            # 소스 구조 미러링
├── conftest.py
├── common/
├── domains/
│   ├── user/
│   ├── event/
│   ├── reservation/
│   └── payment/
└── routers/
```

### 디렉토리 규칙
- **`common/` 은 도메인 무관 코드만** — 특정 엔티티 이름이 들어가면 잘못된 위치
- **새 도메인 추가 = `domains/<name>/` 디렉토리 하나** — model · schema · repository · service 4 파일 기본
- **router 는 1 파일 = 1 도메인** — 한 라우터 파일이 여러 도메인 service 를 묶지 않음
- **`__init__.py` 는 비워둔다** — 도메인 객체 re-export 같은 fancy 한 짓 금지 (간략화)

## 데이터 흐름 (예매 시나리오)

```
Client
  │
  │ POST /reservations  +Authorization: Bearer <jwt>
  ▼
routers/reservations.py
  ├─ Depends(getCurrentUser)      → JWT 검증
  ├─ Depends(getReservationDbSession) → RDS #2 세션
  └─ ReservationService.create(...)
        │
        ▼
domains/reservation/service.py
  ├─ async with session.begin():           ← 트랜잭션 시작
  │    event = await EventRepository(core_session).getById(event_id)  # RDS #1
  │    if not event.hasAvailableSeats(): raise SeatAlreadyTakenError
  │    reservation = await ReservationRepository.create(...)          # RDS #2
  │    await ReservationRepository.lockSeat(...)                      # row lock
  └─ return reservation
        │
        ▼
routers/reservations.py
  └─ ReservationRead.model_validate(reservation)  → JSON 응답
```

### 트랜잭션 경계
- 트랜잭션은 **service 메서드 진입 시 시작 · 정상 종료 시 commit · 예외 시 rollback**
- router 는 트랜잭션을 알지 못한다
- 두 DB 에 걸친 작업은 **첫 DB 의 트랜잭션이 끝난 뒤** 두 번째 DB 호출 (보상 가능한 순서로 설계)

## 환경 설정

### Pydantic Settings 사용

```python
# app/settings.py
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    core_db_url: str = Field(..., alias="CORE_DB_URL")
    reservation_db_url: str = Field(..., alias="RESERVATION_DB_URL")

    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_access_ttl_seconds: int = 60 * 30
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 14


settings = Settings()
```

### 환경별 차이
- `.env.development`, `.env.production` 같은 파일 분리는 **하지 않는다** — 12-factor: 환경 변수로만 차이
- 코드는 환경 분기 (`if settings.env == "production"`) 를 최소화 — 다른 동작이 필요하면 다른 값을 주입

## 기술 스택

| 영역 | 라이브러리 |
|---|---|
| 웹 | `fastapi`, `uvicorn[standard]` |
| ORM | `sqlalchemy>=2.0`, `asyncpg` |
| 마이그레이션 | `alembic` |
| 검증 | `pydantic>=2`, `pydantic-settings` |
| 인증 | `pyjwt`, `passlib[bcrypt]` |
| Redis | `redis>=5` (async client) |
| AWS | `aioboto3` (SQS publish) |
| 로깅 | `structlog` |
| 테스트 | `pytest`, `pytest-asyncio`, `httpx`, `locust` |
| 린트·포맷 | `ruff`, `black`, `mypy` |

> 신규 라이브러리 추가는 [07-workflow.md](07-workflow.md) 의 "권한·의존성 최소화" 규약을 따른다. **인프라 검증과 무관한 라이브러리 도입 금지.**

## 확장 시점 가이드

본 아키텍처는 다음 인프라를 **이미 전제**한다 — 처음부터 함께 코딩한다.

| 항목 | 상태 | 적용 위치 |
|---|---|---|
| ElastiCache (Redis) | **도입됨** | 좌석 hold 한 가지 용도만 |
| SQS + Lambda | **도입됨** | 만료 hold 자동 release 큐 1개 |
| EventBridge | **도입됨** | 정기 트리거 (만료 hold 정리) |
| Multi-AZ RDS | **도입됨** | writer + reader endpoint 분리 |
| CloudWatch | **도입됨** | 메트릭·로그·알람 (기본 메트릭만) |

다음 항목들은 **현재 단계에서 도입하지 않는다.** 본 시스템은 인프라 검증 베드이므로 기능 확장 자체가 목표가 아니다.

| 항목 | 비도입 이유 |
|---|---|
| 결제 PG 연동 | 인프라 검증과 무관. PaymentHistory 는 mock 기록만 |
| 대기열 (Waiting Room) | HPA + 백프레셔로 대신 |
| 이메일·SMS · 알림 | 비핵심 기능 |
| API Gateway · Service Mesh | 모놀리식 단일 서비스 |
| Kafka · 별도 메시지 브로커 | SQS 로 충분 |
| Domain Event 프레임워크 | 도메인 간 비동기 통신 없음 |
| CloudFront · WAF | 정적 자산 없음 |
| Idempotency Redis 캐시 | 결제 미연동이라 핵심 경로 idempotency 불필요 |
| Custom CloudWatch 메트릭 (EMF) | AWS 기본 메트릭으로 충분 |
| Prometheus | CloudWatch 단일 스택 |

> **현재 단계는 단일 모놀리식 FastAPI 앱 + AWS managed 서비스**이다. 위 미도입 항목들을 미리 추상화해두지 않는다.
