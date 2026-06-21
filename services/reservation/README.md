# reservation 서비스

## 개요

좌석 hold→예매 요청→조회/취소를 담당하는 **가장 복잡한** FastAPI 서비스다. `reservations` 테이블 소유로 RDS#2(reservation) 에 속한다. **gRPC 서버**(`GetReservation`, payment 가 소유자 검증에 호출) + **클라이언트**(event `GetEvent`, 좌석 검증) 를 모두 가진다. write 경로는 동기 INSERT 없이 검증→Redis→SQS publish 로 끝나는 **비동기 202** 구조이며, 실제 영속화는 Lambda 가 SQS 를 소비해 수행한다.

## 도메인 · 엔드포인트

도메인 `reservation` — `Reservation`: `reservation_id` UUID PK, `user_id`(인덱스), `event_id`(인덱스), `is_canceled` Bool(소프트 삭제), `reserved_num` Int(좌석 번호), `created_at`/`last_modified`(Date). 다른 RDS 라 FK 없음. `service.py` 는 read/write 서비스로 분리.

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/reservations` | ✓ | 예매 요청→**202**(`reservation_id`). captcha 검증 동반 |
| DELETE | `/reservations/{reservation_id}` | ✓ | 취소 요청→**202** |
| GET | `/reservations` | ✓ | 목록(미영속 ++ DB 병합) |
| GET | `/reservations/seats/occupied` | ✓ | 점유 좌석(DB 비취소 ∪ Redis hold) |
| GET | `/reservations/{reservation_id}` | ✓ | 단건 cache-aside. 소유자 아니면 404 |
| GET | `/captcha/challenge` | - | ALTCHA PoW 챌린지 |
| GET | `/queue/{event_id}` | - | **dev/test 전용** in-memory 대기열 스텁(운영은 API GW→Lambda) |
| GET | `/healthz`·`/readyz` | - | liveness / readiness(DB `SELECT 1` + Redis `ping`) |

## 핵심 동작

**`ReservationWriteService.requestCreate`** (비동기 202 write):

1. **event gRPC** `getTotalSeats(event_id)` → 없으면 `EventNotFoundError`.
2. **좌석 번호 범위 검증** — `1 ≤ reserved_num ≤ total_seats` 아니면 `SeatOutOfRangeError`. 잘못된 좌석을 SQS 에 넣지 않도록 사전 차단.
3. **Redis 잔여 카운터** `seats:remain:{event_id}` — lazy init(`SET nx`) + 원자적 `DECR`. 음수면 `INCR` 복구 후 `EventSoldOutError`. **매진 1차 게이트.**
4. **Redis 좌석 hold** `seat:hold:{event_id}:{reserved_num}` — `SETNX + TTL`. 실패 시 카운터 `INCR` 복구 후 `SeatAlreadyTakenError`.
5. **reservation_id 선발급 + SQS publish** — `group_id=event_id`(같은 이벤트 순서 보장), `dedup_id=reservation_id`. publish 실패 시 hold 삭제 + 카운터 복구의 **양방향 보상**.
6. **낙관적 캐시 적재 + per-user 인덱스** — Lambda 가 DB 에 쓰기 전에도 결제 검증(`GetReservation`)·목록 조회가 hit 하도록 전체 `ReservationRead` 를 `reservation:{id}` 에 적재하고 `reservation:user:{user_id}` set 에 추가.

**`ReservationWriteService.requestCancel`** — cache-first 조회(미영속분은 캐시에만 존재) → owner check(타인은 404 로 가림) → 재취소 차단(`ReservationAlreadyCanceledError`, Lambda 중복 차감 방지) → cancel SQS publish(`event_id` 포함, `dedup_id=cancel:{id}`) → 단건 캐시 무효화 + per-user 인덱스에서 제거.

**`ReservationReadService`**:
- `getById` — 단건 cache-aside. 캐시 value 는 전체 `ReservationRead`(user_id 포함)라 **payment 소유자 검증에 그대로 재사용**.
- `listPaged` — per-user 인덱스로 미영속(SQS 대기) 예매를 추려 DB 결과와 병합(가상 리스트 `[pending ++ db]`). DB 영속·만료분은 조회 시 인덱스에서 정리(**self-heal**).
- `occupiedSeats` — DB 비취소 예매 + Redis 활성 hold 의 **합집합**.

## 의존

- **DB** — RDS#2(reservation) writer/reader(`DB_WRITER_URL`/`DB_READER_URL`). 조회 reader. **write INSERT 는 Lambda** 가 수행.
- **gRPC** — 서버(`GetReservation`, payment 가 호출) + 클라이언트(`EventClient.getTotalSeats`→event `GetEvent`). `GRPC_PORT`, `EVENT_GRPC_TARGET`, `GrpcChannelPool`.
- **SQS** — `SQS_RESERVATION_QUEUE_URL` 로 create/cancel publish. consume 은 lambda 레포.
- **Redis** — `seats:remain:{event_id}`(무기한), `seat:hold:{event_id}:{seat}`(`SEAT_HOLD_TTL_SECONDS`), `reservation:{id}`·`reservation:user:{id}`(`RESERVATION_CACHE_TTL_SECONDS`).
- **libs** — `common`(`errors`·`sqs`·`auth`·`deps`·`captcha`), `connector.pool`, `ccproto.{reservation,event}.v1`, `config.settings`. `messages.py`=create/cancel SQS 페이로드 계약(`version` 필드, lambda 레포와 공유).

---
⬆ [services README로](../README.md)
