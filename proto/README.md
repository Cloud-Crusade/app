# proto — gRPC 계약 (SSOT)

## 1. 개요

`proto/` 는 서비스 간 gRPC 통신 **계약의 단일 진실원(SSOT)** 이다. 마이크로서비스 4개(auth·event·reservation·payment)가 서로를 HTTP 로 직접 호출하는 대신, 여기 정의된 `.proto` 계약으로만 통신한다.

- 패키지 네이밍: `ccproto.<service>.v<n>` (공통 네임스페이스 `ccproto` 로 생성 스텁의 import 충돌 회피).
- 이 `.proto` 들로부터 buf 가 Python 스텁을 생성하며, 산출물은 [libs/protos](../libs/README.md)(`cc-protos`)에 **커밋된 상태**로 들어간다.
- 현재 실제로 호출되는 RPC 는 2개뿐이다 — `EventService.GetEvent`(reservation→event), `ReservationService.GetReservation`(payment→reservation). 나머지 두 패키지(auth·payment)는 **향후 확장 자리 표시용 패키지 선언만** 존재한다(간략화 원칙 — 실제 호출이 생길 때 RPC 추가).

상위 시스템에서의 위치: 서비스 간 협력 계약 → 생성 스텁(libs/protos) → connector 의 채널 풀/서버로 실어 나른다.

## 2. 설계 원칙 & 고려 사항

- **gRPC 만으로 서비스 간 호출** — 서비스가 다른 서비스의 HTTP 엔드포인트를 직접 부르지 않는다. 호출 그래프와 계약을 proto 한 곳에 모은다.
- **계약 최소주의** — "나중에 필요할지 모르는" 필드/RPC 를 미리 넣지 않는다. `GetEvent` 는 좌석 검증에 필요한 `total_seats` 만, `GetReservation` 은 소유자 검증에 필요한 `user_id` 만 반환한다.
- **버전 디렉토리(`v1`)** — breaking 변경은 `v2` 로 분리할 수 있도록 패키지에 버전을 박는다.
- **buf 로 품질 게이트** — STANDARD lint + FILE 단위 breaking 검사. proto 변경 PR 은 `proto-ci` 가 lint/format + 조건부 breaking 을 강제한다.
- **생성물은 커밋** — 런타임/CI 에서 매번 생성하지 않도록 `libs/protos` 에 스텁을 커밋한다(재현성·빌드 단순화).

## 3. 구성

```
proto/
└── ccproto/
    ├── auth/v1/auth.proto                # 패키지 선언만 (RPC 없음)
    ├── event/v1/event.proto              # EventService.GetEvent
    ├── reservation/v1/reservation.proto  # ReservationService.GetReservation
    └── payment/v1/payment.proto          # 패키지 선언만 (RPC 없음)
```

| 파일 | 패키지 | 책임 |
|---|---|---|
| `event/v1/event.proto` | `ccproto.event.v1` | `EventService.GetEvent` — `event_id` → `total_seats`. reservation 이 좌석 범위 검증에 호출 |
| `reservation/v1/reservation.proto` | `ccproto.reservation.v1` | `ReservationService.GetReservation` — `reservation_id` → `user_id`. payment 가 소유자 검증에 호출 |
| `auth/v1/auth.proto` | `ccproto.auth.v1` | 패키지 선언만(현재 gRPC 노출 없음) |
| `payment/v1/payment.proto` | `ccproto.payment.v1` | 패키지 선언만(payment 는 클라이언트만, 서버 없음) |

## 4. 핵심 로직 / 동작

### 스텁 생성

```bash
buf generate        # libs/protos 에 생성 (cc-protos 패키지로 커밋)
```

- 설정은 레포 루트의 `buf.gen.yaml` — **remote 플러그인**으로 `libs/protos` 하위에 `ccproto.<svc>.v1.*` 스텁(`*_pb2.py`, `*_pb2.pyi`, `*_pb2_grpc.py`)을 생성한다.
- 생성된 스텁은 커밋되며, 서비스 코드는 `from ccproto.event.v1 import event_pb2_grpc` 형태로 import 한다.

### 검증

```bash
buf lint                                    # STANDARD 스타일/구조 검증
buf breaking --against '.git#branch=main'   # main 대비 호환성 깨짐 검출
```

- 루트 `buf.yaml` 이 모듈/lint(STANDARD)/breaking(FILE) 정책을 정의한다.
- `proto-ci` 워크플로우가 proto 변경 PR 에서 lint + format + (조건부) breaking 을 자동 수행한다.

### 호출 흐름 (실제 사용 RPC)

```
reservation.requestCreate ──GetEvent(event_id)──► event.grpc_server
                            ◄── total_seats ───┘   (좌석 범위·매진 검증)

payment.requestCreate ──GetReservation(reservation_id)──► reservation.grpc_server
                        ◄────── user_id ──────────────┘   (결제 소유자 검증)
```

서버 측 구현은 각 서비스의 `grpc_server.py`(event·reservation), 클라이언트 래퍼는 `clients.py`(reservation·payment)에 있다. [services/README.md](../services/README.md) 참조.

## 5. 변수·의존관계

- **생성 산출물** → [libs/protos](../libs/README.md) (`cc-protos`). `protobuf>=7.35` 고정, ruff/mypy 제외.
- **채널 풀/서버 부트스트랩** → [libs/connector](../libs/README.md) (`cc-connector`). 멀티 pod round_robin 은 `dns:///<headless>:50051` 타깃 전제.
- **gRPC 타깃 env** — `EVENT_GRPC_TARGET`, `RESERVATION_GRPC_TARGET`, 서버 `GRPC_PORT`(기본 50051). [deploy/README.md](../deploy/README.md) 참조.

---

⬆ [app 대표 README로](../README.md)
