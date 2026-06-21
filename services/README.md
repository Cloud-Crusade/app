# services — 마이크로서비스 레이어

## 1. 개요

`services/` 는 4개의 독립 FastAPI 마이크로서비스다. 각 서비스는 자기 `pyproject.toml`(uv workspace member) · `Dockerfile` · `alembic` 을 가지며, 공통 인프라는 [libs](../libs/README.md) 에서, 서비스 간 계약은 [proto](../proto/README.md) 에서 가져온다.

| 서비스 | 패키지 | RDS | gRPC | 한 줄 요약 |
|---|---|---|---|---|
| [auth](./auth/README.md) | cc-auth | RDS#1 | 없음 | 회원가입·로그인·JWT 발급/갱신 |
| [event](./event/README.md) | cc-event | RDS#1 | 서버 | 이벤트 등록·조회, `GetEvent` 제공 |
| [reservation](./reservation/README.md) | cc-reservation | RDS#2 | 서버+클라이언트 | 좌석 hold→202 예매→조회/취소 (가장 복잡) |
| [payment](./payment/README.md) | cc-payment | RDS#2 | 클라이언트 | 결제 mock 기록 |

상위 시스템에서의 위치: HTTP/gRPC 입구. DB 경계 = 도메인 경계 = 서비스 경계(auth·event→RDS#1, reservation·payment→RDS#2).

## 2. 설계 원칙 & 고려 사항

- **동일 레이어 구조** — 4개 서비스 모두 `main.py` / `db.py` / `domains/<name>/{model,schema,repository,service}` / `routers/` / `alembic` / `Dockerfile` / `tests` 로 미러링된다. 의존성 방향은 `router → service → repository → model` 단방향.
- **비동기 202 write (reservation·payment)** — write 경로는 동기 DB INSERT 를 하지 않는다. 검증 → Redis hold/카운터 → SQS publish → 즉시 `202`. 실제 영속화는 Lambda 레포가 SQS 를 소비해 수행한다.
- **미영속(SQS 대기) 조회 일관성** — Lambda 가 DB 에 쓰기 전에도 단건/목록 조회가 보이도록 **낙관적 캐시 적재 + per-user 인덱스 + self-heal**(DB 영속·만료분은 조회 시 인덱스에서 정리).
- **gRPC 로만 서비스 간 호출** — reservation→event(`GetEvent`: 좌석 검증), payment→reservation(`GetReservation`: 소유자 검증). 멀티 pod 는 `dns:///` headless round_robin.
- **다른 RDS 라 FK 없음** — reservation/payment 테이블은 user/event 와 다른 RDS 라 DB FK 를 걸 수 없다. 참조 무결성은 service 레이어에서 보장(gRPC 검증).
- **토큰만으로 인증** — user 테이블은 auth 소유이므로 다른 서비스는 `getCurrentUserId`(토큰의 user_id 만)로 인증 완결, User DB 조회 안 함.
- **간략화** — 도메인은 4파일(`model/schema/repository/service`)로 평탄. UseCase/Mapper 레이어 없음.

## 3. 구성

```
services/<svc>/
├── <svc>/
│   ├── main.py                 # createApp(...) + 라우터 등록 (+ gRPC 서버 lifespan)
│   ├── db.py                   # 서비스 자기 Base + 엔진/세션 (writer/reader)
│   ├── domains/<name>/
│   │   ├── model.py            # SQLAlchemy 모델
│   │   ├── schema.py           # Pydantic 스키마
│   │   ├── repository.py       # 쿼리 전용
│   │   └── service.py          # 비즈니스 로직 + 트랜잭션
│   ├── routers/                # 도메인별 라우터 + health
│   ├── grpc_server.py          # (event·reservation) gRPC 서버 구현
│   ├── clients.py              # (reservation·payment) gRPC 클라이언트 래퍼
│   └── messages.py             # (reservation·payment) SQS 페이로드 계약
├── alembic/                    # 서비스별 마이그레이션
├── Dockerfile
└── tests/
```

| 서비스 | 도메인 | 주요 파일 |
|---|---|---|
| auth | user | `routers/{auth,users,health}.py` |
| event | event | `grpc_server.py`, `routers/{events,health}.py` |
| reservation | reservation | `grpc_server.py`, `clients.py`, `messages.py`, `routers/{reservations,captcha,queue,health}.py` |
| payment | payment | `clients.py`, `messages.py`, `routers/{payments,health}.py` |

## 4. 핵심 로직 / 동작

### auth (cc-auth) — RDS#1, gRPC 없음

- 도메인 `user` — `User`: `user_id` UUID PK, `user_name` unique, `password_hash`.
- 라우터: `auth`(signup / login / refresh), `users`, `health`.
- **refresh** — DB 를 조회하지 않고 refresh 토큰의 유효성만으로 access 토큰을 재발급(stateless). user 테이블의 소유 서비스라 다른 서비스의 인증 기반이 된다.

### event (cc-event) — RDS#1, gRPC 서버

- 도메인 `event` — `Event`: `event_id` UUID PK, `title` String(20), `body`, `schedule` JSONB, `img_urls` JSONB, `total_seats`.
- `grpc_server.py` — `EventServicer.GetEvent`: `event_id` → `total_seats` 반환. **reservation 이 좌석 검증을 위해 호출**한다.
- 라우터: `events`(등록·조회), `health`.

### reservation (cc-reservation) — RDS#2, gRPC 서버+클라이언트 (가장 복잡)

도메인 `reservation`(다른 RDS 라 FK 없음). `service.py` 가 read/write 서비스로 분리된다.

**`ReservationWriteService.requestCreate`** (비동기 202 write):

1. **event gRPC** 로 `total_seats` 조회 → 없으면 `EventNotFoundError`.
2. **좌석 번호 범위 검증** — 존재하지 않는 좌석을 SQS 에 넣지 않도록 사전 차단.
3. **Redis 잔여 카운터** — lazy init(`SET nx`) + 원자적 `DECR`. 음수면 `INCR` 복구 후 매진(`EventSoldOutError`).
4. **Redis 좌석 hold** — `SETNX + TTL`. 실패 시 잔여 카운터 복구 후 `SeatAlreadyTakenError`.
5. **reservation_id 선발급 + SQS publish** — `group_id=event_id`(같은 이벤트 순서 보장), `dedup_id=reservation_id`. publish 실패 시 hold+카운터 **양방향 보상**.
6. **낙관적 캐시 적재 + per-user 인덱스** — Lambda 가 DB 에 쓰기 전에도 결제 검증(`getById`)·목록 조회가 hit 하도록 전체 `ReservationRead` 를 캐시에 적재하고 `reservation:user:{user_id}` set 에 추가.

**`ReservationWriteService.requestCancel`** — cache-first 조회(미영속분은 캐시에만 존재) → owner check(타인은 404 로 가림) → 재취소 차단(`ReservationAlreadyCanceledError`) → SQS cancel publish → 단건 캐시 무효화 + per-user 인덱스에서 제거.

**`ReservationReadService`**:
- `getById` — 단건 cache-aside(캐시 우선, miss 시 DB 후 적재). 캐시 value 는 전체 `ReservationRead`(user_id 포함)라 **결제 소유자 검증에도 그대로 재사용**된다.
- `listPaged` — 미영속(SQS 대기) 예매를 per-user 인덱스에서 추려 DB 결과와 병합(가상 리스트 `[pending ++ db]`). DB 영속·만료분은 조회 시 인덱스에서 정리(**self-heal**).
- `occupiedSeats` — DB 비취소 예매 + Redis 활성 hold 의 **합집합**.

기타: `grpc_server.py`=`ReservationServicer.GetReservation`(`user_id` 반환, **payment 가 호출**). `clients.py`=`EventClient`. `messages.py`=SQS 페이로드 계약(`version` 필드, **lambda 레포와 공유**). 라우터: `reservations`(POST 202 / DELETE / 목록 / 좌석조회 / 단건), `captcha`(challenge), `health`, `queue`(**dev/test 전용 in-memory 대기열 스텁** — 운영은 API Gateway→Lambda).

### payment (cc-payment) — RDS#2, gRPC 클라이언트만

- `PaymentHistory` — PG 미연동 **mock 기록**.
- `service.py`:
  - `PaymentWriteService.requestCreate` — **reservation gRPC** 로 소유자 검증 → SQS publish(실제 write 는 Lambda) + 낙관적 캐시 적재.
  - `PaymentReadService` — 단건 cache-aside, 목록 병합(reservation 과 동일 패턴). **결제 기록은 불변** → cancel 무효화 없이 TTL 만으로 충분.
- `clients.py`=`ReservationClient`. 라우터: `payments`, `health`.

## 5. 변수·의존관계

- **상위 의존** — 모든 서비스 → [libs](../libs/README.md)(common·config·connector·protos).
- **gRPC 호출** — reservation→event, payment→reservation. 타깃 env `EVENT_GRPC_TARGET` / `RESERVATION_GRPC_TARGET`(`dns:///<headless>:50051`), 서버 `GRPC_PORT`.
- **SQS** — reservation·payment 가 `SQS_RESERVATION_QUEUE_URL` 로 publish. consume 은 lambda 레포.
- **Redis** — reservation·payment 가 좌석 hold·잔여 카운터·캐시·캡차 replay 에 사용.
- **DB** — 각 서비스 `DB_WRITER_URL`/`DB_READER_URL`(자기 롤 크리덴셜). 물리 DB 공유, 테이블 소유권 격리.
- **배포 계약** — 헤드리스 Service·DB 롤·엔드포인트 컷오버·헬스체크(`/healthz`,`/readyz`)는 [deploy/README.md](../deploy/README.md).

---

⬆ [app 대표 README로](../README.md)
