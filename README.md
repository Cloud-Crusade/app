# Cloud Crusade — Ticketing Backend (cc/app)

팀 **C.C (Cloud Crusade)** 의 티켓팅 백엔드 애플리케이션 레이어. 본 레포는 **"AWS 인프라(EKS·RDS·ElastiCache·SQS·Lambda·CloudWatch)의 스파이크 트래픽 흡수 능력 검증"** 이라는 프로젝트의 *애플리케이션 계층* 을 담당한다.

> **한 줄 요약** — FastAPI 기반 마이크로서비스 4개(auth·event·reservation·payment) + 공유 라이브러리 + gRPC 계약을 담은 uv 워크스페이스 모노레포. 목적은 기능 풍부함이 아니라 **인프라가 스파이크를 흡수하는지 검증** 하는 것.

---

## 1. 프로젝트 소개

### 정체성

본 시스템의 목적은 **기능**이 아니라 **인프라 검증**이다. 티켓팅이라는 도메인은 "평시 낮은 트래픽 → 티켓 오픈 순간 수만 RPS 스파이크 → 빠른 감소" 라는 패턴을 만들기 위한 *테스트 베드*일 뿐이다. 따라서 기능은 인프라 검증에 필요한 **3가지로 한정**한다.

| 기능 | 내용 |
|---|---|
| 인증 | 회원가입 · 로그인 · JWT access/refresh 발급·갱신 |
| 행사 관리 | 이벤트 등록 · 조회 |
| 티켓팅 | 좌석 hold → 예매 → 조회/취소 |

> **명시적 비도입**: 결제 PG 연동, 대기열(Waiting Room) 시스템, 이메일/SMS 발송. 결제는 mock 기록만, 대기열은 HPA + 백프레셔로 대신한다.

### 기술 스택

| 영역 | 기술 |
|---|---|
| 언어 | Python 3.12 |
| 웹 | FastAPI + uvicorn (async) |
| ORM / 마이그레이션 | SQLAlchemy 2.0 async + Alembic |
| 검증 | Pydantic v2 / pydantic-settings |
| DB 드라이버 | asyncpg (PostgreSQL), 테스트는 aiosqlite |
| 인증 | JWT (PyJWT, HS256) + bcrypt |
| 캐시·락 | Redis (redis-py async) |
| 비동기 큐 | SQS (aioboto3, **발행만**) |
| 서비스 간 통신 | gRPC (grpcio + buf) |
| 모노레포 | uv workspace |
| proto 툴체인 | buf (lint / breaking / generate) |
| 컨테이너 | Docker (python:3.12-slim, non-root uid 10001) |
| 배포 | EKS (매니페스트는 cc/infra 레포) |
| 린트·타입 | ruff (line 100 / py312, N802·N803·N806 ignore) + mypy strict |
| 테스트 | pytest + pytest-asyncio + httpx.AsyncClient + fakeredis |
| 로깅 | structlog (JSON, stdout) |

---

## 2. 설계 방향 & 고려 사항

전체 그림만 서술한다. 모듈별 상세 설계는 각 모듈 README 로 위임한다.

### 핵심 철학

- **간략화 원칙 (지배적)** — UseCase/Mapper/DTO 레이어 금지, 구현체가 1개면 인터페이스 추상화 금지, 도메인 예외는 실제 분기 케이스만, docstring 최소. 새 추상화는 "두 번째 구현이 필요할 때" 도입한다.
- **모놀리식 → MSA 모노레포 전환** — 단일 FastAPI 앱에서 시작해 단계별 sub-PR(#44~#59)로 서비스 4개를 분리했다. 현재 SSOT 는 `services/`·`libs/` 코드이며, `.claude/rules/` 룰셋 일부는 모놀리식 시절 기준이라 코드가 우선한다.
- **DB 경계 = 도메인 경계 = 서비스 경계** — auth·event → RDS#1, reservation·payment → RDS#2. 물리 DB 는 공유하되 테이블 소유권은 서비스별 격리, **Cross-DB JOIN 금지**.
- **분산/다중 RDS 전제** — 단일 인스턴스 가정 코드 금지. 상태는 외부 저장소(DB·Redis)에만, 동시성 제어는 Redis/DB 로(인메모리 lock 금지).
- **서비스 간 직접 호출 금지 → gRPC** — reservation→event(좌석 검증), payment→reservation(소유자 검증). 멀티 pod 분산은 headless Service + `dns:///` round_robin.
- **분산 트랜잭션(2PC) 금지 → SQS + Lambda 보상** — 두 RDS 에 걸친 atomic 트랜잭션 시도 금지.
- **비동기 202 write (핵심)** — 예매/결제 write 는 동기 DB write 를 하지 않는다. FastAPI 는 검증 → Redis hold/카운터 → SQS publish → 즉시 `202 Accepted`. 실제 INSERT 는 별도 Lambda 레포가 수행한다. FastAPI 는 **낙관적 캐시 적재 + per-user 인덱스** 로 Lambda DB write 전에도 조회가 hit 하도록 한다(미영속 조회 일관성, self-heal).
- **백프레셔** — DB pool `pool_timeout=2s` → 한계 도달 시 빠른 503 반환 → 클라이언트 재시도 유도. 대기열 대신 HPA + Cluster Autoscaler.
- **무중단 엔드포인트 컷오버** — DB/Redis 호스트는 고정 DNS(Route53/RDS Proxy). `pool_pre_ping` + `pool_recycle`(DB), `health_check_interval`(Redis)로 페일오버·주소 변경에 무재시작 재연결.
- **컨테이너 보안** — non-root uid 10001.
- **봇 억제** — 예매 경로 ALTCHA PoW 캡차(fail-closed + replay 방지), stdlib 만 사용.

> 모듈별 상세는 [services/README.md](services/README.md), [libs/README.md](libs/README.md) 참조.

---

## 3. 아키텍처 개요

### 레이어 (서비스 내부)

```
Router (FastAPI)   ← HTTP 입출력, 인증·검증
   │
Service            ← 비즈니스 로직, 트랜잭션 경계, 도메인 예외
   │
Repository         ← SQLAlchemy 쿼리만
   │
Model (ORM)        ← 테이블 매핑 + 상태 메서드
   │
RDS#1 (auth·event)        RDS#2 (reservation·payment)
```

### 비동기 202 write 흐름 (예매)

```
Client ──POST /reservations──► reservation 서비스
                                  │ 1. event gRPC 로 total_seats 검증
                                  │ 2. 좌석 범위 검증
                                  │ 3. Redis 잔여 카운터 원자 DECR (매진 차단)
                                  │ 4. Redis 좌석 hold (SETNX + TTL)
                                  │ 5. reservation_id 선발급 + SQS publish
                                  │ 6. 낙관적 캐시 적재 + per-user 인덱스
                                  └──► 202 Accepted (reservation_id)
                                                │
SQS ──► Lambda(별도 레포) ──► RDS#2 INSERT (실제 영속화)
```

### gRPC 호출 관계

```
reservation ──(GetEvent: total_seats)──► event       (좌석 검증)
payment     ──(GetReservation: user_id)──► reservation (소유자 검증)
```

멀티 pod 는 headless Service + `EVENT_GRPC_TARGET=dns:///event-grpc:50051` 형식으로 서브채널을 풀링(round_robin)한다.

---

## 4. 모듈 구성

### 디렉토리 트리

```
app/
├── pyproject.toml          # uv 워크스페이스 루트 + 공통 ruff/mypy/pytest
├── buf.yaml, buf.gen.yaml  # proto lint/breaking + 생성 플러그인
├── conftest.py             # 테스트 env 기본값 + 공통 async fixture
├── .env.example
├── .claude/rules/          # 9개 룰셋 (일부 모놀리식 시절 기준)
├── .github/workflows/      # app-ci · proto-ci · ecr-push · convention_check
│
├── proto/ccproto/          # gRPC 계약 SSOT
│   ├── auth/v1/            event/v1/
│   ├── reservation/v1/     payment/v1/
│
├── libs/                    # 공유 패키지 (uv workspace member)
│   ├── common/   (cc-common)     config/    (cc-config)
│   ├── connector/(cc-connector)  protos/    (cc-protos, buf 산출물·커밋됨)
│
├── services/               # 4개 마이크로서비스 (각자 Dockerfile·alembic)
│   ├── auth/   event/   reservation/   payment/
│
└── deploy/README.md        # 배포 계약 (cc/infra 가 충족)
```

### 모듈 한 줄 요약

| 모듈 | 패키지 | 요약 |
|---|---|---|
| proto | — | 서비스 간 gRPC 계약(SSOT). buf 로 lint/breaking/generate |
| libs/common | cc-common | 도메인 무관 공유 인프라(app factory·db·security·redis·sqs·captcha·deps) |
| libs/config | cc-config | Settings 단일 클래스 + settings 싱글톤 |
| libs/connector | cc-connector | gRPC 채널 풀(round_robin) + aio 서버 부트스트랩 |
| libs/protos | cc-protos | buf generate 산출물(`ccproto.<svc>.v1.*`) |
| services/auth | cc-auth | 인증(signup/login/refresh), RDS#1, gRPC 없음 |
| services/event | cc-event | 이벤트 등록·조회, RDS#1, gRPC 서버(GetEvent) |
| services/reservation | cc-reservation | 예매(좌석 hold→202→조회/취소), RDS#2, gRPC 서버+클라이언트 |
| services/payment | cc-payment | 결제 mock 기록, RDS#2, gRPC 클라이언트 |

### 세부 README — 읽는 순서

1. **[proto/README.md](proto/README.md)** — gRPC 계약(SSOT). 먼저 서비스 간 인터페이스 계약을 이해한다.
2. **[libs/README.md](libs/README.md)** — 모든 서비스가 의존하는 공유 패키지 레이어(common/config/connector/protos). 공통 인프라 동작을 익힌다.
3. **[services/README.md](services/README.md)** — 4개 마이크로서비스(auth/event/reservation/payment). 비동기 write·캐시·gRPC 의 실제 구현.
4. **[deploy/README.md](deploy/README.md)** — 배포 계약(cc/infra 가 충족할 헤드리스 Service·DB 롤·엔드포인트 컷오버·헬스체크).

---

## 5. 실행 방법

### 로컬 (uv 워크스페이스)

```bash
# 의존성 설치 (워크스페이스 전체)
uv sync

# 서비스 실행 (각 서비스 동일 패턴, --package 만 교체)
uv run --package cc-reservation uvicorn reservation.main:app --host 0.0.0.0 --port 8000
uv run --package cc-auth        uvicorn auth.main:app        --host 0.0.0.0 --port 8000
uv run --package cc-event       uvicorn event.main:app       --host 0.0.0.0 --port 8000
uv run --package cc-payment     uvicorn payment.main:app     --host 0.0.0.0 --port 8000
```

`ENV=development|test` 면 부팅 시 `dev_bootstrap` 이 자기 Base 테이블을 `create_all` 하고, reservation 은 `/queue` 스텁을 등록한다. 로컬 인프라는 docker-compose(postgres/redis), AWS 는 LocalStack 으로 대체한다.

### 테스트

```bash
uv run pytest          # testpaths = services, libs / --import-mode=importlib
```

### Docker 빌드

빌드 컨텍스트는 **레포 루트**(libs + services 워크스페이스를 함께 COPY). 2단계 캐싱 — ① `pyproject` COPY + `uv sync --no-install-workspace` ② 소스 COPY + `uv sync --package cc-<svc>`. non-root uid 10001, `UV_CACHE_DIR`, `EXPOSE 8000`.

### Alembic 마이그레이션 (서비스별)

```bash
# 각 서비스의 alembic 디렉토리에서, 배포 시 해당 DB 롤로
alembic -c services/<svc>/alembic/alembic.ini upgrade head
```

### 배포

본 레포는 **이미지 빌드 + ECR push** 까지만 담당한다(`.github/workflows/ecr-push.yml`). EKS 매니페스트·롤아웃·DB 롤·Terraform 은 cc/infra 레포. 상세 계약은 [deploy/README.md](deploy/README.md).

---

## 6. 컨벤션 합의 사항

> 아래 표기는 팀 협업 규약이며 CI(`convention_check`)로 강제된다.

### Github 컨벤션

#### Issue
**템플릿을 준수**
이슈 타이틀 형태: `[카테고리]: 이슈 제목`

카테고리
- Feature: 기능 추가, 기능 변경
- Refactor: 리팩토링, 구조 변경
- Bug: 발생한 버그 목록
- Chore: 의존성, 문서 작업 등 코드 외 작업 (별도의 의존성 작업만 추가할 경우)

EX
`[Feature] OAuth 2.0 추가`
`[Refactor] Ansible 모듈 리팩토링`

#### Branch
브랜치 이름 형태: `카테고리/#이슈번호/브랜치명`

카테고리
- feature: 기능 추가, 기능 변경
- refactor: 리팩토링, 구조 변경
- fix: 버그 수정
- chore: 의존성, 문서 작업 등 코드 외 작업 (별도의 의존성 작업만 추가할 경우)

#### Commit
커밋 메시지 형태: `[카테고리]: 커밋 내용`

카테고리
- FEAT: 기능 추가, 기능 변경
- REFAC: 리팩토링, 구조 변경
- FIX: 버그 수정, 오류 수정
- CHORE: 의존성 추가, 코드 외 작업

EX
`[FEAT]: OAuth2.0 추가 - Google, Naver Authentication`
`[CHORE]: pytest 의존성 추가`

#### Pull Request
**템플릿을 준수**

제목 형태: `[카테고리#이슈번호] PR 제목`

카테고리
- FEAT: 기능 추가, 기능 변경
- REFAC: 리팩토링, 구조 변경
- FIX: 버그 수정, 오류 수정
- CHORE: 의존성 추가, 코드 외 작업
**카테고리는 커밋과 동일**

EX
`[FEAT#18] Google, Naver OAuth 2.0 추가`

> **표기 차이 요약** — Commit `[FEAT]:` (콜론, 4개 카테고리, DOCS 없음) / PR `[FEAT#N]` (콜론 없음) / Issue `[Feature]` (full-word) / Branch `카테고리/#이슈번호/브랜치명`. Label 매핑: Feature→`enhancement`, Refactor→`refactor`, Bug→`bug`, Chore→`chore`.

### Code 컨벤션

#### Naming

**Class**
클래스는 PascalCase로 작성

기본 작성 규칙
- 각 클래스는 명명된 모델 및 엔티티에 맞춰 작성
- 객체 지향 원칙에 따른 엔티티 작성
- 필요한 경우 인터페이스를 위한 추상 클래스 작성 후 상속

EX
`class User`
`class Payment`

**Method**
메소드는 camelCase로 작성

기본 작성 규칙
- public 메소드는 일반문자로 시작
- private 메소드는 언더바(_) 로 시작
- parameter는 최대한 엔티티 요소를 함축한 단어로 작성
- Restful API 키워드보다는 메소드의 동작 방식을 기준으로 명명

EX
`def getUser()`
`def createUser()`

**Variable**
변수는 snake_case로 작성

기본 작성 규칙
- 각 변수는 사용처, 알고리즘, 아키텍처에 맞는 명칭 사용
- 의미 없는 변수 (ex: data1, document 등) 사용 금지
- 속성 변수는 외부에서 최대한 사용하지 않도록 배제 (의존성 감소를 위한 규칙)

EX
`user = User()`

> camelCase 메서드 허용을 위해 ruff `N802`/`N803`/`N806` 룰을 ignore 한다. 타입 힌트 필수(`X | None`, `list[str]`), 주석/커밋/로그는 한국어 단일(식별자는 ASCII), line 100, mypy strict, SQLAlchemy 2.0 `Mapped`, Pydantic v2.

#### Architecture
기본은 DDD 아키텍처에 기반한 설계
모듈형으로 설계

아키텍처 일반화
- common: 공용 모듈
- domains: 각 서비스 도메인 별 모듈
- routers: 각 API 라우터 (Spring - Controllers)

### CI 강제

| 워크플로우 | 트리거 | 역할 |
|---|---|---|
| `app-ci` | PR | `uv sync` + `pytest` |
| `proto-ci` | proto 변경 PR | `buf lint` + `buf format` + 조건부 `buf breaking` |
| `ecr-push` | main 머지 / 수동 | paths-filter 로 변경 서비스만 빌드 → ECR push(태그 = SHA + latest) → `EKS_ENABLED` 시 rollout restart |
| `convention_check` | PR | 커밋·PR 제목 lint |

> 테스트 커버리지 목표 — 전체 70% / `service.py` 90% / `security.py` 95%. 테스트 함수명은 영어 ASCII, fixture 는 camelCase.

---

## 7. 팀원 작업 역할

| 기여자 | 담당 영역 |
|---|---|
| 김주현 (juhy0987, 레포 오너) | 애플리케이션 전체 — 서비스·도메인·공유 libs·proto·아키텍처 사실상 단독 오너십. MSA 전환 전체, 캐시/캡차/대기열 스텁 |
| hjh1346 | CI/CD · Docker 빌드 파이프라인 (#14 Docker, #16 ECR push, #10 pytest CI) |
| mshjgr | EKS 롤링 업데이트 CD (#42) |

---

## 8. 참고

### 연관 레포 (Cloud-Crusade Org)

| 레포 | 역할 | 링크 |
|---|---|---|
| app | 애플리케이션(본 레포) | https://github.com/Cloud-Crusade/app |
| web | 프론트엔드 | https://github.com/Cloud-Crusade/web |
| lambda | SQS consumer / 실제 DB write | https://github.com/Cloud-Crusade/lambda |
| infra | Terraform · EKS 매니페스트 | https://github.com/Cloud-Crusade/infra |

### 내부 문서

- [deploy/README.md](deploy/README.md) — 배포 계약(헤드리스 Service·DB 롤·엔드포인트 컷오버·헬스체크)
- [.claude/rules/](.claude/rules/) — 9개 개발 룰셋(아키텍처~트래픽). 일부는 모놀리식 시절 기준이므로 코드가 우선

### 단일 출처

- 인프라 다이어그램 · ERD: Notion 프로젝트 계획서
