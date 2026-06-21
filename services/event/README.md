# event 서비스

## 개요

이벤트 등록·조회·수정·삭제를 담당하는 FastAPI 서비스다. `event` 테이블 소유로 RDS#1(core) 에 속한다. **gRPC 서버**로 `GetEvent` 를 제공해, reservation 이 좌석 검증 시 `total_seats` 를 가져갈 수 있게 한다.

## 도메인 · 엔드포인트

도메인 `event` — `Event`: `event_id` UUID PK, `user_id`(등록자, 인덱스), `title` String(20), `body` Text(nullable), `schedule` JSONB(시작·종료 검증), `img_urls` JSONB list, `total_seats` Integer(≥1), `created_at`/`last_modified`(Date).

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| GET | `/events` | - | 목록(page/size, `created_at desc`). reader |
| GET | `/events/{event_id}` | - | 단건. 없으면 `EventNotFoundError`(404). reader |
| POST | `/events` | ✓ | 토큰 user_id 로 등록. writer |
| PATCH | `/events/{event_id}` | ✓ | 부분 수정. writer |
| DELETE | `/events/{event_id}` | ✓ | 삭제(204). writer |
| GET | `/healthz`·`/readyz` | - | liveness / readiness(core DB `SELECT 1`) |

## 핵심 동작

- **`GetEvent` gRPC** — `EventServicer.GetEvent`: `event_id`(str)→`total_seats`(int) 반환. UUID 파싱 실패는 `INVALID_ARGUMENT`, 미존재는 `NOT_FOUND` 로 abort. **reservation 의 좌석 범위 검증에 쓰이는 최소 응답.**
- **gRPC 서버 lifespan** — `main.py` 가 startup 에서 `registerEventService` 로 서버 기동(`GRPC_PORT`), shutdown 에서 `grace=5` 로 정리.
- **schedule 검증** — Pydantic `Schedule`(start_at/end_at) 가 종료>시작을 강제.

## 의존

- **DB** — RDS#1(core) writer/reader. 조회 reader, 변경 writer.
- **gRPC** — 서버만(`GetEvent` 제공). 클라이언트 호출 없음.
- **SQS / Redis** — 없음.
- **libs** — `common`(`app_factory`·`db`·`errors`·`auth`), `connector.server`, `ccproto.event.v1`, `config.settings`.

---
⬆ [services README로](../README.md)
