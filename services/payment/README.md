# payment 서비스

## 개요

결제를 **mock 기록**(PG 미연동)하는 FastAPI 서비스다. `payment_histories` 테이블 소유로 RDS#2(reservation) 에 속한다. **gRPC 클라이언트**로 reservation 의 `GetReservation` 을 호출해 결제 전 소유자를 검증한다. write 경로는 동기 INSERT 없이 SQS publish 로 끝나는 **비동기 202** 구조다.

## 도메인 · 엔드포인트

도메인 `payment` — `PaymentHistory`: `payment_history_id` UUID PK, `user_id`(인덱스), `reservation_id`(인덱스), `payment_method` String(20), `created_at`(Date). 다른 RDS 라 FK 없음. **불변 기록**(취소·상태 컬럼 없음).

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/payments` | ✓ | 소유자 검증→SQS publish→**202**(`payment_history_id`) |
| GET | `/payments` | ✓ | 목록. 미영속 캐시 + DB 병합(page/size) |
| GET | `/payments/{payment_history_id}` | ✓ | 단건 cache-first. 소유자 아니면 404 |
| GET | `/healthz`·`/readyz` | - | liveness / readiness(DB `SELECT 1` + Redis `ping`) |

## 핵심 동작

- **`PaymentWriteService.requestCreate`** — ① reservation gRPC(`getOwnerId`)로 소유자 검증(불일치·미존재 시 `ReservationNotFoundError`, 잘못된 메시지 publish 사전 차단) → ② `PaymentCreateMessage` 를 SQS publish(`group_id=reservation_id`, `dedup_id=payment_history_id`) → ③ **낙관적 캐시 적재**(Lambda 가 DB 에 쓰기 전에도 조회 hit 하도록) + per-user 인덱스 추가. 실제 INSERT 는 Lambda.
- **`PaymentReadService`** — 단건 cache-aside(miss 시 DB 후 적재), 목록은 per-user 인덱스로 미영속분을 DB 결과와 병합. DB 영속·만료분은 조회 시 인덱스에서 정리(**self-heal**).
- **불변이라 무효화 없음** — 결제 기록은 취소되지 않으므로 캐시 무효화 로직 없이 **TTL 만으로** 충분.

## 의존

- **DB** — RDS#2(reservation) reader. write 는 SQS→Lambda 경로라 라우터에 writer 미노출.
- **gRPC** — 클라이언트만. `ReservationClient.getOwnerId`→reservation `GetReservation`. 타깃 `RESERVATION_GRPC_TARGET`, `GrpcChannelPool`.
- **SQS** — `SQS_RESERVATION_QUEUE_URL` 로 publish(`SqsPublisher`). consume 은 lambda 레포.
- **Redis** — `payment:{id}`(단건), `payment:user:{user_id}`(set). TTL `PAYMENT_CACHE_TTL_SECONDS`.
- **libs** — `common`(`errors`·`auth`·`deps`·`sqs`), `connector.pool`, `ccproto.reservation.v1`, `config.settings`. `messages.py`=SQS 페이로드 계약(`version` 필드, lambda 레포와 공유).

---
⬆ [services README로](../README.md)
