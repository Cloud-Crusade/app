# libs — 공유 패키지 레이어

## 1. 개요

`libs/` 는 4개 마이크로서비스가 공통으로 의존하는 **공유 패키지 레이어**다. uv 워크스페이스 멤버 4개로 구성되며, 각 서비스는 자기 `pyproject.toml` 에서 필요한 것을 의존성으로 가져온다.

| 패키지 | 디렉토리 | 책임 |
|---|---|---|
| cc-common | `libs/common/common/` | 도메인 무관 공유 인프라(앱 팩토리·db·security·redis·sqs·captcha·deps·예외) |
| cc-config | `libs/config/config/` | `Settings` 단일 클래스 + `settings` 싱글톤 |
| cc-connector | `libs/connector/connector/` | gRPC 채널 풀 + aio 서버 부트스트랩 |
| cc-protos | `libs/protos/ccproto/` | buf generate 산출물(`ccproto.<svc>.v1.*`, 커밋됨) |

상위 시스템에서의 위치: 서비스 코드(`services/`)가 의존하는 **하부 인프라 계층**. 도메인 로직은 여기 없다 — "어떤 엔티티" 가 들어가면 잘못된 위치다.

## 2. 설계 원칙 & 고려 사항

- **도메인 무관** — common 에 `User`/`Reservation` 같은 엔티티 이름이 등장하면 안 된다. 공통 인프라(미들웨어·DB 엔진·보안·캐시)만 둔다.
- **모든 서비스가 같은 부팅 경로** — `app_factory.createApp(...)` 하나로 미들웨어·예외 핸들러·lifespan 을 통일한다. 서비스 `main.py` 는 라우터만 꽂는다.
- **설정은 한 클래스** — 환경 변수 분산을 막기 위해 `cc-config` 의 단일 `Settings` 로 모든 튜닝값(DB·Redis·JWT·SQS·좌석/캐시 TTL·캡차·gRPC)을 노출한다. 하드코딩 대신 변수화.
- **발행만(SQS)** — FastAPI 측은 SQS publish 만 한다. consume/실제 DB write 는 Lambda 레포 책임. 그래서 `sqs.py` 는 `SqsPublisher` 뿐이다.
- **fail-closed 보안** — 캡차 검증은 실패 시 통과시키지 않고 막는다(fail-closed) + replay 방지.
- **스파이크 대비 백프레셔** — DB 엔진은 `pool_size=10/max_overflow=0/pool_timeout=2`. 풀 소진 시 대기하지 않고 빠르게 503.
- **무중단 컷오버** — DB `pool_pre_ping`+`pool_recycle`, Redis 전역 풀 + `health_check_interval` 로 페일오버·엔드포인트 변경에 무재시작 재연결.

## 3. 구성

```
libs/
├── common/   (cc-common)
│   └── common/
│       ├── app_factory.py         # createApp(...) — 미들웨어+예외핸들러+lifespan
│       ├── db.py                  # NAMING_CONVENTION, TimestampMixin, buildEngine
│       ├── security.py            # bcrypt + JWT access/refresh
│       ├── auth.py                # getCurrentUserId 의존성
│       ├── captcha.py             # ALTCHA PoW (stdlib only)
│       ├── errors.py              # DomainError 평면 계층
│       ├── exception_handlers.py  # 도메인/검증/무결성/일반 핸들러
│       ├── redis.py               # buildRedis (전역 풀 + health_check)
│       ├── sqs.py                 # SqsPublisher (발행만)
│       ├── deps.py                # getRedisClient / getReservationSqs / verifyReservationCaptcha
│       ├── dev_bootstrap.py       # dev/test 만 create_all
│       ├── logging.py             # structlog JSON 설정
│       └── tests/
│
├── config/   (cc-config)
│   └── config/settings.py         # Settings + settings 싱글톤
│
├── connector/(cc-connector)
│   └── connector/
│       ├── pool.py                # GrpcChannelPool (round_robin LB)
│       └── server.py              # startServer(register, port)
│
└── protos/   (cc-protos)
    └── ccproto/<svc>/v1/*_pb2*.py # buf 산출물 (ruff/mypy 제외)
```

## 4. 핵심 로직 / 동작

### common — `app_factory.py`

`createApp(...)` 가 모든 서비스의 FastAPI 인스턴스를 만든다. 포함하는 것:

- `RequestIdMiddleware` — 요청마다 `X-Request-ID` 발급, structlog contextvar 에 바인딩.
- CORS 미들웨어 — `cors_allow_origins` 화이트리스트 + preflight(OPTIONS) 처리(cc/web 교차 출처 대응).
- 예외 핸들러 4개 — `DomainError` / 검증 / 무결성 / 일반(5xx). 응답은 `{code, message, details}` 평면 형식.
- `lifespan` — 부팅/셧다운 훅(dev/test 면 `dev_bootstrap` 으로 자기 Base 테이블 생성).

서비스 `main.py` 는 `createApp(...)` 호출 후 자기 라우터만 `include_router` 한다.

### common — `db.py`

- `NAMING_CONVENTION` — index/constraint 이름 자동화(마이그레이션 일관성).
- `TimestampMixin` — `created_at`/`last_modified` 공통 필드.
- `buildEngine(...)` — postgres 엔진 팩토리. `pool_size=10`, `max_overflow=0`, `pool_pre_ping`, `pool_recycle`, **`pool_timeout=2`(백프레셔)**. 풀 소진 시 대기 없이 즉시 실패 → 503.

### common — `security.py` / `auth.py`

- `security.py` — bcrypt 해시 + JWT access/refresh 발급·검증(HS256).
- `auth.py` — `getCurrentUserId` 의존성. **토큰에서 `user_id` 만 꺼낸다(User DB 조회 안 함)**. MSA 라 user 테이블은 auth 서비스 소유이므로, 다른 서비스는 토큰만으로 인증을 완결한다.

### common — `captcha.py` / `deps.py`

- `captcha.py` — ALTCHA Proof-of-Work 캡차. **stdlib 만** 사용(외부 의존성 없음).
- `deps.py` 의 의존성:
  - `getRedisClient` — 전역 풀에서 Redis 클라이언트.
  - `getReservationSqs` — `SqsPublisher` 주입.
  - `verifyReservationCaptcha` — **fail-closed**(검증 실패 시 차단) + **replay 방지**(Redis 로 사용 챌린지 1회 소비).

### common — `redis.py` / `sqs.py` / `dev_bootstrap.py`

- `redis.py` — `buildRedis()` 전역 ConnectionPool + `health_check_interval`(idle 커넥션 재검증 → 페일오버 시 새 커넥션이 DNS 재해석).
- `sqs.py` — `SqsPublisher`(aioboto3). **publish 만** 제공(group_id/dedup_id 지원).
- `dev_bootstrap.py` — `ENV` 가 development|test 일 때만 자기 Base 의 `create_all`. 운영은 alembic 으로만.

### config — `settings.py`

`Settings`(pydantic-settings) 단일 클래스로 모든 튜닝값을 노출하고 `settings` 싱글톤으로 import 한다. 주요 그룹:

| 그룹 | 변수(alias) |
|---|---|
| DB | `DB_WRITER_URL`, `DB_READER_URL`, `DB_POOL_RECYCLE_SECONDS` |
| Redis | `REDIS_URL`, `REDIS_HEALTH_CHECK_INTERVAL_SECONDS` |
| JWT | `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_ACCESS_TTL_SECONDS`, `JWT_REFRESH_TTL_SECONDS` |
| AWS/SQS | `AWS_REGION`, `AWS_ENDPOINT_URL`, `SQS_RESERVATION_QUEUE_URL` |
| 좌석/캐시 TTL | `SEAT_HOLD_TTL_SECONDS`, `RESERVATION_CACHE_TTL_SECONDS`, `PAYMENT_CACHE_TTL_SECONDS` |
| 캡차 | `CAPTCHA_ENABLED`, `CAPTCHA_HMAC_SECRET`, `CAPTCHA_COMPLEXITY` |
| gRPC | `GRPC_PORT`, `EVENT_GRPC_TARGET`, `RESERVATION_GRPC_TARGET` |
| CORS | `CORS_ALLOW_ORIGINS` |

> 예매 캐시 TTL(기본 300s)은 결제 캐시(기본 3600s)보다 짧다 — 예매는 취소로 변경 가능해 staleness 를 짧게 제한.

### connector — `pool.py` / `server.py`

- `pool.py` — `GrpcChannelPool`. round_robin LB + keepalive. **`dns:///` headless 타깃 전제**(L4 고정 ClusterIP 면 클라이언트 round_robin 이 무력화되므로). `size=1`.
- `server.py` — `startServer(register, port)`. `grpc.aio` 서버 부트스트랩(event·reservation 의 gRPC 서버가 사용).

### protos — `ccproto.<svc>.v1.*`

[proto/README.md](../proto/README.md) 의 `.proto` 로부터 `buf generate` 한 산출물. `protobuf>=7.35` 고정. 생성 코드라 ruff/mypy 검사에서 제외.

## 5. 변수·의존관계

- **하위 의존 없음** — libs 는 서비스에 의존하지 않는다(단방향: services → libs).
- **cc-common → cc-config** — 엔진/Redis/SQS 팩토리가 `settings` 값을 읽는다.
- **cc-connector → cc-protos** — 채널 풀/서버가 생성 스텁을 실어 나른다.
- **테스트 연동** — 루트 `conftest.py` 가 공통 async fixture(`coreEngine`/`coreSession`/`redis`/`sqsMock`/`client`)를 제공하고, 각 서비스는 `serviceBase`/`sessionDeps` 를 override 한다.

---

⬆ [app 대표 README로](../README.md)
