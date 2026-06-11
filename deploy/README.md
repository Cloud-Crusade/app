# 배포 계약 (cc/infra 가 구현)

본 레포(cc/app)는 **서비스 이미지 빌드·ECR push 까지** 담당한다(`.github/workflows/ecr-push.yml`,
path 필터로 변경 서비스만, 공유 `libs`/`proto` 변경 시 전체). EKS 매니페스트·롤아웃·DB 롤은
cc/infra 가 구현한다. 아래는 각 서비스가 정상 동작하기 위해 cc/infra 가 충족해야 하는 계약이다.

## 서비스 (이미지 = `ticketing-<svc>`)

| 서비스 | 이미지 | HTTP | gRPC 서버 | 물리 DB |
|---|---|---|---|---|
| auth | ticketing-auth | 8000 | 없음 | RDS#1 |
| event | ticketing-event | 8000 | 50051 (EventService) | RDS#1 |
| reservation | ticketing-reservation | 8000 | 50051 (ReservationService) | RDS#2 |
| payment | ticketing-payment | 8000 | 없음 (클라이언트만) | RDS#2 |

## gRPC 연결 풀 (멀티 pod) — #48

- event·reservation 의 gRPC 서버는 **headless Service**(`clusterIP: None`)로 노출해야 한다.
  일반 ClusterIP 는 L4 고정이라 클라이언트측 round_robin 이 동작하지 않는다.
- 클라이언트 타깃 env 는 `dns:///<headless-service>:50051` 형식이어야 모든 pod 서브채널을
  풀링(round_robin)한다.
  - reservation: `EVENT_GRPC_TARGET=dns:///event-grpc:50051`
  - payment: `RESERVATION_GRPC_TARGET=dns:///reservation-grpc:50051`

## DB — 테이블 소유권 격리 (#49)

- 물리 DB 는 공유(RDS#1: auth·event, RDS#2: reservation·payment), **테이블 소유권은 서비스별 격리**.
- 서비스별 DB 롤/크리덴셜을 발급하고 자기 테이블에만 `GRANT` (cc/infra terraform).
  각 서비스는 `DB_WRITER_URL`/`DB_READER_URL` 로 자기 롤 크리덴셜을 받는다.
- 마이그레이션은 `services/<svc>/alembic` (서비스별). 배포 시 해당 서비스 롤로 `alembic upgrade head`.

### 엔드포인트 컷오버 (주소 변경 — 이전·blue-green)

- `DB_*_URL` 의 **호스트는 고정 DNS(Route53 private CNAME) 또는 RDS Proxy** 엔드포인트여야 한다.
  실제 RDS 가 바뀌어도 앱 URL/env 는 불변 → 무재시작·무중단.
- **컷오버 절차**: 새 DB 복제 → CNAME 타깃(또는 Proxy target) 변경 → 구 DB 연결 차단.
  앱은 `pool_pre_ping`(죽은 커넥션 감지 → 새 커넥션이 DNS 재해석)으로 새 엔드포인트에 재연결.
- 수렴 속도는 `DB_POOL_RECYCLE_SECONDS` 로 조절(컷오버 시 짧게, 평시 1800).
- Multi-AZ 페일오버는 엔드포인트 DNS 가 고정이라 위 메커니즘으로 자동 처리(별도 조치 불필요).

## 환경변수

각 서비스 공통(`.env.example` 참조): `ENV`, `DB_WRITER_URL`, `DB_READER_URL`, `REDIS_URL`,
`JWT_SECRET`, `SQS_RESERVATION_QUEUE_URL`, `GRPC_PORT`, 캡차·캐시 TTL 등. gRPC 타깃은 위 표 참조.

## 헬스체크

- `/healthz` (liveness), `/readyz` (readiness — 서비스별 자기 DB + 사용하는 의존성 점검).
