# 스파이크 트래픽 대응 · 스케일링 · 부하 테스트

## 핵심 원칙

> **간략화 우선** — 본 시스템은 AWS 인프라 검증 베드. 비즈니스 정교함 (대기열 시스템·VIP·우선순위 등) 은 도입 안 한다. **좌석 hold + 백프레셔 + HPA + Locust** 4 가지 메커니즘만으로 검증한다.

## 트래픽 패턴

```
RPS
 │
 │                  ┌───┐
 │                  │   │  ← 티켓 오픈 (수만 RPS, 수분간)
 │                  │   │
 │ ──────┐          │   │  ┌──────────  ← 잔여 좌석 정리 트래픽
 │       │          │   │  │
 │ 평시  └──────────┘   └──┘     평시
 │ ~수십 RPS
 └────────────────────────────────────────► 시간
```

- **평시**: 매우 낮음
- **오픈 직후 5~10분**: 폭증 (목표 2만 RPS+)
- **이후**: 빠르게 감소

## 핵심 전략 3가지

### 1. 좌석 점유 hold (Redis)

목적: 결제 진행 중인 좌석을 일시 점유 → DB 부하 ↓, race 회피.

흐름:

```
1) 클라이언트가 좌석 선택 → POST /reservations/holds
2) Redis SETNX seat:hold:{event_id}:{seat_no} (TTL 5분)
3) 성공 시 → hold_token 발급 → 클라이언트에 반환
4) 클라이언트가 5분 이내 확정 진행 → POST /reservations/confirm {hold_token}
5) 확정 성공 → DB 에 reservation INSERT + payment_history mock 기록 + Redis hold key 삭제
6) 5분 만료 → Redis TTL 자동 해제 → 다른 사용자 가능 + Lambda 가 좌석 잔여 카운터 보정
```

구현은 [03-domain-and-data.md](03-domain-and-data.md) 의 "분산 lock — Redis (ElastiCache)" 참조.

### 2. 좌석 잔여 카운터 (Redis)

목적: DB row lock 만으로 수만 RPS 의 좌석 잔여 검사 불가능. Redis 카운터로 대체.

```
1) 이벤트 오픈 시 Redis INIT:
   SET seats:remain:{event_id} <total_seats>

2) hold 시 DECR seats:remain:{event_id}
   결과 ≥ 0 → hold 성공
   결과 < 0 → INCR 복구 + SeatAlreadyTakenError

3) 확정 시: DB 영구 기록 (INCR 안 함)

4) hold TTL 만료: Lambda (`seat-release` 큐) 가 INCR 로 보정
```

#### 주의
- **Redis 와 DB 정합성** — 일시 disagree 가능. Lambda 가 정기 reconciliation
- **Redis 다운 시** — DB row lock 으로 fallback (성능 ↓, 동작 유지)

### 3. 백프레셔 (Backpressure)

목적: DB·Redis 가 한계 도달 시 빠르게 fail 반환 → 클라이언트 재시도 유도. **대기열 시스템 대체.**

```python
# DB 풀에 타임아웃 명시 — 대기 X
engine = create_async_engine(
    settings.core_reader_url,
    pool_size=30,
    max_overflow=0,
    pool_timeout=2,     # 2초 안에 못 가져오면 raise
)
```

#### 정책
- **DB 커넥션 풀 만료** → 503 즉시 반환 (대기 X)
- **Redis 응답 timeout** → 503
- **HPA 가 미처 따라가지 못할 때** → ALB 5xx → 클라이언트 retry

#### Retry-After 헤더
- 503 응답 시 `Retry-After: <초>` 헤더 권장 (1~3 초 random)
- 클라이언트가 exponential backoff 적용 가정

> **대기열 (Waiting Room) 토큰 큐 패턴은 도입하지 않는다** — 인프라 검증 목적이므로 HPA + 백프레셔로 대신한다. 도입이 필요해지면 본 룰셋을 갱신.

## EKS HPA (Horizontal Pod Autoscaler)

### 정책

스파이크는 ALB 5xx → CloudWatch alarm → 운영자 알림 순서로 인지된다. HPA 가 빠르게 스케일 아웃 해야 알람 전에 흡수된다.

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ticketing-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ticketing-api
  minReplicas: 2
  maxReplicas: 50
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: {type: Utilization, averageUtilization: 60}
    - type: Resource
      resource:
        name: memory
        target: {type: Utilization, averageUtilization: 70}
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0       # 즉시 스케일 아웃
      policies:
        - type: Percent
          value: 100                       # 한 번에 2배까지
          periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300     # 5분 안정화 후 줄임
      policies:
        - type: Percent
          value: 50
          periodSeconds: 60
```

### 규칙
- **scaleUp 즉시** — 스파이크는 분 단위로 끝남
- **scaleDown 보수적** — 후속 트래픽 + 비용 최적화 사이 균형
- **`maxReplicas` 는 RDS max_connections 고려** — Pod 수 × pool_size 가 한계 초과 시 의미 없음 ([08-aws-infrastructure.md](08-aws-infrastructure.md))
- **메트릭은 CPU + Memory 만** — 커스텀 메트릭 (RPS) 도입 X. AWS 기본 메트릭 정책 ([04-error-handling.md](04-error-handling.md)) 일관

### Cluster Autoscaler

Pod 가 늘어도 노드가 부족하면 Pending. 노드 자동 추가:
- Cluster Autoscaler (또는 Karpenter) 설치
- 노드 그룹 max size 충분히 (예: min 2, max 20)
- Pod resource requests 정확히 설정 → 스케줄러가 옳게 판단

## 부하 테스트 (Locust)

목적: HPA·DB·Redis 가 목표 RPS (2만+) 를 실제로 흡수하는지 검증. **인프라 검증의 핵심 도구.**

### 디렉토리

```
loadtest/
├── locustfile.py
└── scenarios/
    ├── ticket_open.py        # 오픈 시점 스파이크 (메인 검증 시나리오)
    └── steady_browse.py      # 평시 조회
```

### 메인 시나리오 — ticket_open

핵심 흐름: 로그인 → 이벤트 조회 → 좌석 hold → 예매 확정.

```python
# loadtest/scenarios/ticket_open.py
from locust import HttpUser, task, between
import uuid

class TicketOpenUser(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        r = self.client.post("/auth/login", json={"email": "load@example.com", "password": "..."})
        self.token = r.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def listEvents(self):
        self.client.get("/events", headers=self.headers)

    @task(1)
    def holdAndConfirm(self):
        # 1. hold
        seat = f"A-{uuid.uuid4().hex[:4]}"
        r = self.client.post(
            "/reservations/holds",
            json={"event_id": 1, "seat_no": seat},
            headers=self.headers,
        )
        if r.status_code != 201:
            return  # 백프레셔 503 / 좌석 점유 409 → 정상 동작
        hold_token = r.json()["hold_token"]

        # 2. confirm
        self.client.post(
            "/reservations/confirm",
            json={"hold_token": hold_token, "payment_method": "mock"},
            headers=self.headers,
        )
```

### 실행

```bash
# 단일 머신
locust -f loadtest/scenarios/ticket_open.py --host=https://api.ticketing.example.com

# 분산 (master + workers)
locust -f loadtest/scenarios/ticket_open.py --master --host=...
locust -f loadtest/scenarios/ticket_open.py --worker --master-host=...
```

### 측정 기준

| 항목 | 목표 |
|---|---|
| RPS | ≥ 20,000 (1분 sustained) |
| p99 latency | ≤ 1000ms (목록 조회), ≤ 2000ms (좌석 hold) |
| 5xx 비율 | < 0.5% (백프레셔 503 은 5xx 가 아닌 클라이언트 retry 신호로 별도 집계) |
| HPA 스케일 아웃 시간 | < 60s |
| DB writer CPU | < 80% |
| RDS replica lag | < 1s |

### 안티 패턴
- **운영 환경 부하 테스트** — staging 환경에서만
- **단일 사용자 토큰 재사용** — rate limit 효과로 부정확. 사전에 다수 사용자 시드

## 로컬 개발 환경에서 분산 기능

EKS · ElastiCache 없이 로컬에서도 동일 코드가 동작해야 한다.

```yaml
# docker-compose.yml (로컬)
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      CORE_DB_URL: postgresql+asyncpg://user:pass@core_db:5432/core
      RESERVATION_DB_URL: postgresql+asyncpg://user:pass@reservation_db:5432/reservation
      REDIS_URL: redis://redis:6379/0
  core_db:
    image: postgres:16-alpine
  reservation_db:
    image: postgres:16-alpine
  redis:
    image: redis:7-alpine
```

- **SQS·Lambda 로컬 미지원** — 좌석 잔여 보정 Lambda 는 로컬에서 동작하지 않음. 정합성 검증은 staging 에서
- **CloudWatch 미지원** — stdout 출력으로 동작

## 안티 패턴

### 금지
- **DB 트랜잭션 안에서 외부 API 호출** — 락 시간 폭증 → 스파이크 시 데드락
- **Python `asyncio.Lock` 으로 좌석 점유** — 다중 Pod 무력화
- **메모리 캐시 (`@lru_cache`) 로 좌석 잔여 계산** — Pod 간 불일치
- **대기열 토큰 큐 도입** — 본 룰셋 범위 밖 (백프레셔로 대신)
- **Idempotency Redis 캐시 도입** — 결제 PG 미연동이라 불필요
- **HPA 없이 사전 over-provisioning** — 비용 폭증, 본 시스템 가치 (비용 최적화) 위배
- **부하 테스트를 prod 환경에서** — staging only
