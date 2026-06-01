# 티켓팅 서비스 개발 룰셋

이 디렉토리는 **티켓팅 서비스 백엔드 (FastAPI)** 개발을 위한 룰셋입니다. 본 서비스는 **AWS 인프라 (EKS·RDS·ElastiCache·SQS·CloudWatch) 의 스파이크 대응 능력을 검증하기 위한 테스트 베드**입니다. 따라서 기능은 인프라 검증에 필요한 **최소한** 으로 한정합니다.

## 시스템 범위 (필독)

본 서비스는 다음 3가지 기능만 가집니다.

1. **인증** — 회원가입 · 로그인 · JWT 토큰 발급/갱신
2. **행사 관리** — 이벤트 등록·조회 (관리자 등록, 사용자 조회)
3. **티켓팅** — 좌석 점유 (hold) → 예매 확정 → 예매 조회/취소

### 명시적으로 다루지 않는 것
- **결제 PG 연동 X** — `PaymentHistory` 는 ERD 호환 위해 존재하지만 **단순 기록만** (Mock). 외부 결제 API 호출·재시도·콜백 처리 없음
- **대기열 (Waiting Room) 시스템 X** — 인프라 검증 목적이므로 HPA + 백프레셔로 대신
- **이메일·SMS 발송 X**
- **관리자 대시보드·통계 X**
- **추천·검색·필터 고도화 X**
- **CDN·정적 자산 최적화 X**

> 기능 추가 제안이 들어와도 "인프라 테스트 베드" 라는 정체성을 우선합니다. 새 기능은 인프라 검증에 **반드시 필요한 경우** 에만 본 룰셋을 갱신하며 추가.

각 엔티티의 세부 속성은 [03-domain-and-data.md](03-domain-and-data.md) 의 ERD 스키마 섹션 참조.

### 기본 기술 스택

| 영역 | 기술 |
|---|---|
| 웹 프레임워크 | FastAPI (asgi, async) |
| ORM | SQLAlchemy 2.0 async + Alembic |
| 검증 | Pydantic v2 |
| DB 드라이버 | asyncpg (PostgreSQL) |
| 인증 | JWT (access + refresh) |
| 캐시·락 | Redis (ElastiCache) — 좌석 hold 용도 |
| 큐·비동기 | SQS + Lambda (만료 hold 자동 release 1개 큐) |
| 컨테이너 | Docker + EKS (Kubernetes) |
| 트래픽 | ALB + ACM |
| 모니터링 | CloudWatch (Logs · Metrics · Alarms) — 기본 메트릭만 |
| IaC | Terraform |
| CI/CD | GitHub Actions → ECR → EKS |
| 부하 테스트 | Locust |
| 테스트 | pytest + pytest-asyncio + httpx.AsyncClient |
| 서버 | uvicorn |
| 로깅 | structlog (JSON, stdout) |

### 단일 출처
- **인프라 다이어그램·ERD**: [Notion 프로젝트 계획서](https://www.notion.so/36de8b70b7aa80f59e54d08bb5c96b06)
- 위 다이어그램 변경 시 본 룰셋도 함께 갱신

## 룰셋 구성

룰셋은 도메인별로 7개 파일로 분리됩니다.

### [01-architecture.md](01-architecture.md)
**전체 아키텍처 및 디렉토리 구조**

- DDD 기반 모듈형 레이어 (common / domains / routers)
- 의존성 방향 (router → service → repository → model)
- 비동기 처리 원칙 (async/await, 세션 관리)
- 환경 설정 (settings, 다중 환경)
- 데이터 흐름과 트랜잭션 경계

> 새 개발자는 반드시 이 문서부터 읽고 시작합니다.

### [02-api-implementation.md](02-api-implementation.md)
**API 라우터·엔드포인트 구현 표준**

- APIRouter 분할 정책 (도메인별)
- 요청·응답 Pydantic 스키마 패턴
- 의존성 주입 (DB 세션, 현재 사용자, 권한)
- HTTP 상태 코드 및 응답 표준
- JWT 인증 흐름과 보호 라우트
- 페이지네이션·필터링·정렬

### [03-domain-and-data.md](03-domain-and-data.md)
**도메인 로직 · 데이터 처리**

- 도메인 모듈 구조 (model / schema / repository / service)
- SQLAlchemy 모델 정의 및 관계 매핑
- Repository 패턴과 쿼리 작성
- 트랜잭션 경계와 동시성 (예매 race 조건)
- Alembic 마이그레이션 정책
- 비즈니스 검증과 도메인 예외

### [04-error-handling.md](04-error-handling.md)
**에러 처리 · 로깅 · 모니터링**

- 도메인 예외 계층 (DomainError → HTTPException 변환)
- 글로벌 예외 핸들러
- 재시도 정책 (외부 결제 PG 호출 등)
- 구조화 로깅 (structlog, request_id 전파)
- Prometheus 메트릭 정의
- 헬스체크 및 알림 규칙

### [05-testing.md](05-testing.md)
**테스트 전략 및 품질 게이트**

- pytest + pytest-asyncio 구성
- TestClient / httpx.AsyncClient 사용 패턴
- 비동기 DB 픽스처 (testcontainers / SQLite-asyncpg)
- 도메인별 테스트 디렉토리 미러링
- 커버리지 목표 (전체 70%, 핵심 로직 90%+)
- CI 워크플로우 (lint + test + coverage)

### [06-code-style.md](06-code-style.md)
**코드 스타일 · 컨벤션**

- Python 포맷팅 (Black, Ruff, isort)
- 타입 힌트 필수 영역
- 네이밍 (Class PascalCase / Method camelCase / Variable snake_case)
- 비동기 코드 패턴
- 주석·문서 한국어 단일 정책
- 안티 패턴 목록
- Git 커밋 · 브랜치 · PR 컨벤션

### [07-workflow.md](07-workflow.md)
**AI 작업 진행 규약**

- 이슈 먼저 (issue-first) 생성 정책
- 자율 진행 정책 (승인 요청 최소화)
- AWS · Terraform · EKS 변경 destructive 구분
- Commit-per-TODO 정책
- PR 자동 생성 정책
- 권한 최소화 원칙
- 이슈·PR 분류 메타데이터 정책

### [08-aws-infrastructure.md](08-aws-infrastructure.md)
**AWS 인프라 · IaC · CI/CD**

- 인프라 토폴로지 (VPC, EKS, ALB, RDS, ElastiCache, SQS, Lambda)
- Terraform 디렉토리·모듈 정책
- EKS Manifest 표준 (Deployment, Ingress, probe, graceful shutdown)
- ElastiCache (Redis) key prefix · TTL 표준
- SQS + Lambda + EventBridge 표준 큐 정의
- Dockerfile 표준 · 보안 (IAM IRSA, Secrets Manager)
- GitHub Actions CI/CD (OIDC, ECR, EKS rollout)

### [09-traffic-and-scaling.md](09-traffic-and-scaling.md)
**스파이크 트래픽 대응 · 스케일링 · 부하 테스트**

- 좌석 점유 hold (Redis)
- 좌석 잔여 Redis 카운터
- 백프레셔 (Backpressure) — DB 풀 timeout → 503
- EKS HPA + Cluster Autoscaler 정책
- Locust 부하 테스트 시나리오 · 측정 기준

## Quick Start

### 새 개발자

1. **시작**: [01-architecture.md](01-architecture.md) — 시스템 전체 그림
2. **스타일**: [06-code-style.md](06-code-style.md) — 작성 규칙
3. **흐름**: [02-api-implementation.md](02-api-implementation.md) → [03-domain-and-data.md](03-domain-and-data.md) 순으로 읽기

### 작업 유형별

**새 API 엔드포인트 추가**
1. [02-api-implementation.md](02-api-implementation.md) — 라우터·스키마 작성
2. [03-domain-and-data.md](03-domain-and-data.md) — service·repository 추가
3. [04-error-handling.md](04-error-handling.md) — 도메인 예외 정의
4. [05-testing.md](05-testing.md) — 테스트 작성

**새 도메인 엔티티 추가**
1. [01-architecture.md](01-architecture.md) — 디렉토리 구조 확인
2. [03-domain-and-data.md](03-domain-and-data.md) — 모델·스키마·repository 생성
3. Alembic revision 생성 후 마이그레이션
4. [05-testing.md](05-testing.md) — 도메인 테스트 추가

**프로덕션 이슈 디버깅**
1. [04-error-handling.md](04-error-handling.md) — Incident Response 절차
2. CloudWatch Logs Insights 로그 검색 + Metrics 확인
3. request_id 로 요청 추적

**스파이크 트래픽 대응 검증**
1. [09-traffic-and-scaling.md](09-traffic-and-scaling.md) — 좌석 hold·대기열·HPA·Locust
2. staging 환경에서 Locust 부하 테스트
3. CloudWatch 로 HPA 스케일·RDS·Redis 부하 확인

**AWS 인프라 변경**
1. [08-aws-infrastructure.md](08-aws-infrastructure.md) — Terraform 모듈 구조
2. `terraform plan` 결과 확인 후 사용자 승인
3. apply 후 CloudWatch 알람·헬스체크 확인

## 프로젝트 성격 — 간략화 원칙 (필독)

본 프로젝트는 **AWS 인프라 검증을 위한 단순 티켓팅 서비스**입니다. 엔터프라이즈급 추상화·미래 확장 일반화·복잡한 비즈니스 정책은 **명시적으로 금지**합니다.

### 금지 사항
- **계층을 위한 계층 추가 금지** — UseCase·Interactor·Mapper·DTO Layer 등 router/service/repository/model 외 임의 레이어 도입 금지
- **인터페이스 우선 설계 금지** — 구현체가 1개뿐인데 ABC/Protocol 로 미리 추상화하지 않는다. 두 번째 구현이 필요해질 때 추출
- **불필요한 디자인 패턴 금지** — Factory·Builder·Strategy 등은 실제 분기점이 2개 이상 생겼을 때만 도입
- **확장 포인트 사전 노출 금지** — "나중에 다른 결제 PG도 붙일 수 있게" 같은 가정 금지
- **과도한 설정화 금지** — 환경 변수·yaml 로 빼는 건 환경별로 실제 달라지는 값만
- **장황한 docstring·주석 금지** — WHY 가 비자명할 때만 한 줄. WHAT 은 코드가 말한다
- **불필요한 예외 계층 금지** — 도메인 예외는 실제 분기되는 케이스만 정의 (`UserNotFound`, `SeatAlreadyTaken` 정도)
- **비핵심 기능 추가 금지** — 위 "시스템 범위" 외 기능은 어떤 형태로도 도입 금지

### 권장 사항
- **단순 직선 흐름 우선** — `router → service → repository` 한 흐름이면 충분. helper 함수가 1번만 쓰이면 인라인
- **3번 반복되면 그때 추출** — 비슷한 코드 2개는 OK, 3번째에 공통화
- **DDD 는 디렉토리 구조까지만** — Aggregate Root·Domain Event 등 전술 패턴 도입은 명시 합의 후
- **무엇이든 의심스러우면 더 단순한 쪽으로** — 룰 충돌 시 간략화 원칙이 우선
- **인프라 검증 목적 우선** — 기능 풍부함 < 인프라 동작 확인. 핵심 흐름이 끝까지 동작하는 게 중요

> AI 에게 작업을 맡길 때 "엔터프라이즈급으로 잘 짜줘" 류 표현 금지. 이 룰셋의 기본값은 **최소한**입니다.

## 인프라 전제 — AWS · 분산 환경 · 다중 RDS

본 시스템은 **AWS 위 분산 처리 환경**을 전제로 합니다. 단일 인스턴스 가정의 코드는 작성 금지입니다.

### 핵심 인프라
- **EKS Pod (FastAPI)** — 다중 인스턴스. HPA 로 스파이크 시 스케일 아웃 ([09](09-traffic-and-scaling.md))
- **RDS × 2** — core (user/event) + reservation (reservation/payment). 각각 writer + reader endpoint
- **ElastiCache (Redis)** — 좌석 hold, idempotency, 대기열 토큰
- **SQS + Lambda + EventBridge** — 비동기 작업, 세션 누수 방지, 정기 cleanup
- **ALB + ACM** — 인입 (TLS 종료)
- **CloudWatch** — Logs / Metrics / Alarms

### 다중 RDS 정책
- **예약 DB 는 별도 RDS 로 분리** — `Reservation`, `PaymentHistory` 는 트래픽·정합성 요구사항이 다른 도메인과 분리된 인스턴스에서 운용
- **DB 경계 = 도메인 경계** — DB 가 다르면 cross-DB JOIN 금지. 필요 시 service 레이어에서 식별자 기반 조회로 조합
- **DB 별 세션·엔진 분리** — `getCoreWriterSession` / `getCoreReaderSession` / `getReservationWriterSession` / `getReservationReaderSession` 4 종
- **트랜잭션은 단일 DB 내에서만** — 두 DB 에 걸친 atomic 트랜잭션 시도 금지 (2PC 도입 X). 도메인 이벤트 또는 보상 트랜잭션 패턴 사용
- **읽기는 reader 우선** — read-after-write 만 writer

### 분산 환경 전제
- **상태는 외부 저장소에만** — 프로세스 메모리 캐시·전역 변수에 비즈니스 상태 보관 금지
- **동시성 제어는 DB·Redis 로** — 인메모리 lock 사용 금지. row lock / unique constraint / Redis 분산 lock 활용
- **idempotency 보장** — 결제·예매 핵심 경로는 클라이언트가 동일 요청을 재시도해도 안전하도록 설계
- **그레이스풀 셧다운** — k8s rolling update 대응. SIGTERM 처리 + readiness 503 전환

> 인프라 다이어그램·ERD 의 단일 출처는 [Notion 프로젝트 계획서](https://www.notion.so/36de8b70b7aa80f59e54d08bb5c96b06). 변경 시 본 룰셋도 함께 갱신합니다.

## 핵심 원칙

### 1. 명시적 비동기
- I/O 경계 (DB·HTTP·캐시) 는 모두 async
- 동기 함수 안에서 `asyncio.run()` 금지 (이벤트 루프 충돌)
- CPU bound 작업은 `run_in_executor` 명시 사용

### 2. 레이어 분리
- Router 는 검증·인증·응답 형식화만 담당
- Service 는 비즈니스 로직과 트랜잭션 경계
- Repository 는 SQL/ORM 호출만
- Model 은 도메인 상태와 불변식만

### 3. 데이터 정합성
- 예매 등 동시성 핵심 경로는 명시적 row lock 또는 unique constraint + 재시도
- 모든 외부 노출 입력은 Pydantic 검증 통과 후 사용
- 트랜잭션은 service 레이어에서 시작·종료

### 4. 관측성
- 모든 요청에 request_id 부여 및 로그 전파
- 도메인 이벤트는 INFO, 예상 외 처리는 WARN, 실패는 ERROR
- Prometheus 메트릭은 도메인별 분리

### 5. 테스트 우선
- 신규 기능은 테스트와 함께 PR 제출
- DB 의존 테스트는 fixture 로 격리
- 단위 테스트는 외부 시스템 mocking

## 개발 워크플로우

### 코딩 전

1. **요구사항 명확화** — 어떤 엔티티·동작에 영향을 주는가
2. **관련 룰 확인** — 위 룰셋에서 해당 섹션 읽기
3. **설계 스케치** — 데이터 흐름·실패 시나리오·테스트 포인트

### 코딩 중

1. [06-code-style.md](06-code-style.md) 의 네이밍·포맷 준수
2. 레이어 경계 침범 금지 — router 가 직접 SQLAlchemy 세션을 들고 쿼리하지 않음
3. 비동기 함수 안에서 동기 I/O 사용 금지
4. 도메인 예외는 [04-error-handling.md](04-error-handling.md) 의 계층 사용

### 코딩 후

1. **셀프 리뷰** ([06-code-style.md](06-code-style.md) 체크리스트)
2. **품질 게이트**: ruff + black + mypy + pytest 통과 확인
3. **PR 생성**: [07-workflow.md](07-workflow.md) 의 컨벤션 적용

## 공통 패턴

### 라우터 정의

```python
from fastapi import APIRouter, Depends, status
from app.common.deps import getCurrentUser, getDbSession
from app.domains.reservation.schemas import ReservationCreate, ReservationRead
from app.domains.reservation.service import ReservationService

router = APIRouter(prefix="/reservations", tags=["reservations"])


@router.post("", response_model=ReservationRead, status_code=status.HTTP_201_CREATED)
async def createReservation(
    payload: ReservationCreate,
    user=Depends(getCurrentUser),
    session=Depends(getDbSession),
) -> ReservationRead:
    service = ReservationService(session)
    reservation = await service.create(user_id=user.id, payload=payload)
    return ReservationRead.model_validate(reservation)
```

### 서비스 + 트랜잭션

```python
from app.common.errors import SeatAlreadyTakenError

class ReservationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._reservations = ReservationRepository(session)
        self._events = EventRepository(session)

    async def create(self, user_id: int, payload: ReservationCreate) -> Reservation:
        async with self._session.begin():
            event = await self._events.getForUpdate(payload.event_id)
            if not event.hasAvailableSeats():
                raise SeatAlreadyTakenError(event_id=event.id)
            reservation = await self._reservations.create(
                user_id=user_id, event_id=event.id, seat_no=payload.seat_no,
            )
            await self._events.decrementAvailableSeats(event.id)
            return reservation
```

### 도메인 예외 → HTTP 응답

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.common.errors import DomainError

app = FastAPI()

@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )
```

## Claude 와의 협업

작업을 Claude 와 진행할 때:

1. **룰 명시 인용** — "02-api-implementation.md 의 라우터 분할 규칙에 따라…"
2. **도메인 명시** — "Reservation 도메인의 create 흐름을…"
3. **검증 요청** — "이 구현이 03-domain-and-data.md 의 트랜잭션 경계 정책을 만족하는지 확인"

## 룰 업데이트

룰은 살아 있는 문서입니다.

### 갱신 시점
- 새 패턴이 코드베이스에 자리 잡았을 때
- 운영 이슈로 부족한 부분이 드러났을 때
- 새 기술·라이브러리가 도입됐을 때

### 갱신 절차
1. 디스커션으로 변경 제안
2. 해당 룰셋 파일 수정
3. 구조 변경 시 본 README 갱신
4. 팀 공지 후 신규 코드부터 적용

## 추가 자료

### 외부 문서
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0 (async): https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- Pydantic v2: https://docs.pydantic.dev/latest/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/

### 내부 문서
- API 명세: `docs/api/`
- 배포 가이드: `docs/deployment/`
- 런북: `docs/runbooks/`

---

**원칙**: 룰은 일관성·품질·유지보수성을 위해 존재합니다. 모호하면 룰을 따르고, 룰이 커버하지 못하는 경우가 생기면 그것이 룰을 개선할 기회입니다.
