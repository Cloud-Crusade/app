# 도메인 로직 · 데이터 처리

## 핵심 원칙

> **간략화 우선** — Aggregate Root, Repository 인터페이스 추상화, UnitOfWork 같은 전술적 DDD 패턴은 도입 금지. 도메인은 `model + schema + repository + service` 4 파일 구조로 충분하다.

## 도메인 모듈 구조

```
domains/<name>/
├── __init__.py        # 비워둔다
├── model.py           # SQLAlchemy ORM 모델 (1개 또는 소수)
├── schema.py          # Pydantic 요청/응답 스키마
├── repository.py      # 쿼리·INSERT/UPDATE/DELETE
└── service.py         # 비즈니스 로직 + 트랜잭션
```

### 추가 금지
- `dto.py`, `mapper.py`, `dao.py`, `factory.py` — 불필요
- `entities/`, `value_objects/`, `aggregates/` 하위 분할 — 1개 도메인은 평탄 구조

### 추가 허용 (실제 필요할 때만)
- `domains/<name>/events.py` — 도메인 이벤트가 실제로 2 군데 이상 발행될 때
- `domains/<name>/policy.py` — 정책 함수가 service 외에서도 호출될 때

## 엔티티 도메인 매핑

| 도메인 | RDS | 주요 책임 |
|---|---|---|
| `user` | core (RDS #1) | 회원가입, 인증, 프로필 |
| `event` | core (RDS #1) | 이벤트 등록, 일정 관리 |
| `reservation` | reservation (RDS #2) | 예매 생성·취소, 좌석 할당 |
| `payment` | reservation (RDS #2) | 결제 내역 기록, 결제 상태 관리 |

> 같은 RDS 안에서는 FK 관계 자유, 다른 RDS 면 ID 필드만 보유 (FK 제약 없음).

## ERD 스키마 (확정본)

본 ERD 는 [Notion 의 ERD 다이어그램](https://www.notion.so/36de8b70b7aa80f59e54d08bb5c96b06) 을 단일 출처로 한다.

```
users                          events                         reservations                    payment_histories
─────────────                  ─────────────                  ─────────────                   ─────────────
PK user_id (uuid)              PK event_id (uuid)             PK reservation_id (uuid)        PK payment_history_id (uuid)
   user_name varchar(255)      FK user_id                     FK user_id                      FK user_id
   created_at date                title varchar(20)           FK event_id                     FK reservation_id
                                   body text NULL                is_canceled bool                payment_method char(20)
                                   schedule jsonb                 reserved_num int                create_at date
                                   img_urls jsonb                 created_at date
                                   created_at date                last_modified date
                                   last_modified date
```

### 관계
- `users 1:N events` (FK: `events.user_id` — 이벤트 등록자)
- `users 1:N reservations`
- `events 1:N reservations` (FK: `reservations.event_id`)
- `users 1:N payment_histories`
- `reservations 1:N payment_histories` (재시도·환불 이력 누적 가능)

### 주의 사항
- **`reservations` 와 `payment_histories` 는 RDS #2** — `users.user_id`, `events.event_id` 는 RDS #1 에 존재하므로 **DB 레벨 FK 제약을 걸 수 없다**
- → `reservations.user_id` 같은 컬럼은 **인덱스만 부여**, FK 제약 없음
- → 참조 무결성은 service 레이어에서 보장 (생성 직전 존재 검증)
- **`title varchar(20)` 은 다이어그램 기준** — 실제 운영 시 부족하면 마이그레이션으로 확장 (단순 ALTER)
- **`schedule jsonb`** — 시작·종료·세부 일정. Pydantic 스키마로 구조 검증 필수
- **`img_urls jsonb`** — 이미지 URL 리스트. S3 키 또는 CDN URL 저장
- **`created_at` 타입이 `date`** (ERD 기준) — 시각이 필요하면 `timestamptz` 로 마이그레이션 검토 (운영 결정사항)

## SQLAlchemy 모델

### 베이스 정의

```python
# app/common/db.py
from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class CoreBase(DeclarativeBase):
    metadata = MetaData(naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    })


class ReservationBase(DeclarativeBase):
    metadata = MetaData(naming_convention=CoreBase.metadata.naming_convention)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )
```

- **베이스는 DB 별로 분리** — Alembic autogenerate 가 두 DB 의 테이블을 섞지 않도록
- **타임스탬프는 Mixin** — `created_at`, `updated_at` 은 모든 테이블 기본 필드
- **`naming_convention`** — index/constraint 이름 자동화 (마이그레이션 일관성)

### 모델 예시

```python
# app/domains/event/model.py
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.db import CoreBase, TimestampMixin


class Event(CoreBase, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    venue: Mapped[str] = mapped_column(String(200), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    available_seats: Mapped[int] = mapped_column(Integer, nullable=False)

    def hasAvailableSeats(self) -> bool:
        return self.available_seats > 0

    def decrementSeats(self, count: int = 1) -> None:
        if self.available_seats < count:
            from app.common.errors import SeatAlreadyTakenError
            raise SeatAlreadyTakenError(event_id=self.id)
        self.available_seats -= count
```

### 규칙
- **타입 힌트 필수** — `Mapped[...]` 사용 (SQLAlchemy 2.0 스타일)
- **`__tablename__` 명시** — 자동 생성 X
- **도메인 메서드는 모델에 둔다** — `hasAvailableSeats()` 같은 상태 판단은 service 가 아닌 model 책임
- **무거운 로직 금지** — 외부 호출·트랜잭션·다른 도메인 참조는 model 에서 하지 않음
- **컬럼명은 snake_case** — Pydantic 스키마와 일치

### 관계 매핑 (같은 RDS 내에서만)

```python
# app/domains/reservation/model.py — RDS #2
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.db import ReservationBase, TimestampMixin


class Reservation(ReservationBase, TimestampMixin):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)   # 다른 RDS, FK 없음
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 다른 RDS, FK 없음
    seat_no: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmed")

    payments: Mapped[list["PaymentHistory"]] = relationship(back_populates="reservation")


class PaymentHistory(ReservationBase, TimestampMixin):
    __tablename__ = "payment_histories"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int] = mapped_column(ForeignKey("reservations.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    reservation: Mapped["Reservation"] = relationship(back_populates="payments")
```

- **같은 RDS 내 관계만 FK + `relationship`**
- **다른 RDS 참조는 ID 필드만** — `user_id`, `event_id`. FK 제약·`relationship` 사용 금지
- **N+1 회피** — `selectinload`/`joinedload` 명시 ([Repository 섹션](#repository-패턴) 참조)

## Writer / Reader 세션 정책

RDS 가 각각 writer + reader endpoint 를 가진다. 의존성도 4 종으로 분리한다.

| 의존성 | DB | 용도 |
|---|---|---|
| `getCoreWriterSession` | RDS #1 writer | User · Event 변경 |
| `getCoreReaderSession` | RDS #1 reader | User · Event 조회 |
| `getReservationWriterSession` | RDS #2 writer | Reservation · Payment 변경 |
| `getReservationReaderSession` | RDS #2 reader | Reservation · Payment 조회 |

### 라우팅 규칙
- **단순 조회 → reader** — 목록, 단건 조회, 검색
- **쓰기 → writer** — INSERT/UPDATE/DELETE
- **read-after-write → writer** — 방금 쓴 데이터를 같은 요청에서 즉시 읽어야 하면 writer (reader 는 replication lag 가능)
- **트랜잭션 내부는 writer** — `async with writer_session.begin():` 안에서는 모두 writer

### 잘못된 패턴
```python
# 나쁨 — reader 에서 트랜잭션 시작 시도
async with reader_session.begin():
    await repo.create(...)  # ❌ reader 는 읽기 전용
```

### 좋은 패턴
```python
@router.get("", response_model=Page[EventRead])
async def listEvents(
    page: int = 1,
    size: int = 20,
    session: AsyncSession = Depends(getCoreReaderSession),  # ✅ 조회 → reader
):
    ...

@router.post("", response_model=ReservationRead, status_code=201)
async def createReservation(
    payload: ReservationCreate,
    user: User = Depends(getCurrentUser),
    res_writer: AsyncSession = Depends(getReservationWriterSession),  # ✅ 쓰기 → writer
    core_reader: AsyncSession = Depends(getCoreReaderSession),        # ✅ 이벤트 조회 → reader
):
    ...
```

## Repository 패턴

### 정의
- **SQL 호출 전용 계층** — 비즈니스 검증·다른 도메인 참조 금지
- **세션을 생성자로 주입** — 호출자가 트랜잭션 경계 제어

```python
# app/domains/event/repository.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.event.model import Event


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def getById(self, event_id: int) -> Event | None:
        return await self._session.get(Event, event_id)

    async def getForUpdate(self, event_id: int) -> Event | None:
        stmt = select(Event).where(Event.id == event_id).with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def listPaged(
        self, *, page: int, size: int, venue: str | None = None,
    ) -> tuple[list[Event], int]:
        stmt = select(Event)
        if venue is not None:
            stmt = stmt.where(Event.venue == venue)
        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(total_stmt)).scalar_one()
        items_stmt = stmt.order_by(Event.starts_at.desc()).offset((page - 1) * size).limit(size)
        items = list((await self._session.execute(items_stmt)).scalars().all())
        return items, total

    async def create(self, event: Event) -> Event:
        self._session.add(event)
        await self._session.flush()
        return event
```

### 규칙
- **메서드 네이밍은 동작 기준** — `getById`, `getForUpdate`, `listPaged`, `create`, `markRefunded`
- **`raise` 금지** — 없으면 `None` 반환, 존재 검사는 service 에서
- **`commit()` 금지** — 트랜잭션은 service 의 `async with session.begin():` 가 담당
- **`flush()` 는 ID 필요할 때만**
- **N+1 우려가 있으면 `selectinload`/`joinedload` 명시**

```python
# 관계 로딩 예시
from sqlalchemy.orm import selectinload

async def getWithPayments(self, reservation_id: int) -> Reservation | None:
    stmt = (
        select(Reservation)
        .options(selectinload(Reservation.payments))
        .where(Reservation.id == reservation_id)
    )
    return (await self._session.execute(stmt)).scalar_one_or_none()
```

## Service 레이어

### 정의
- **비즈니스 로직과 트랜잭션 경계**
- **도메인 예외 발생 지점** — HTTPException 대신 도메인 예외 raise
- **두 RDS 가 모두 필요한 흐름은 service 가 두 세션을 보유**

```python
# app/domains/reservation/service.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import EventNotFoundError, SeatAlreadyTakenError
from app.domains.event.repository import EventRepository
from app.domains.reservation.model import Reservation
from app.domains.reservation.repository import ReservationRepository
from app.domains.reservation.schema import ReservationCreate


class ReservationService:
    def __init__(
        self,
        reservation_session: AsyncSession,
        core_session: AsyncSession,
    ) -> None:
        self._reservation_session = reservation_session
        self._core_session = core_session
        self._reservations = ReservationRepository(reservation_session)
        self._events = EventRepository(core_session)

    async def create(self, *, user_id: int, payload: ReservationCreate) -> Reservation:
        # 1. RDS #1: 이벤트 검증 + 좌석 차감 (단일 DB 트랜잭션)
        async with self._core_session.begin():
            event = await self._events.getForUpdate(payload.event_id)
            if event is None:
                raise EventNotFoundError(event_id=payload.event_id)
            if not event.hasAvailableSeats():
                raise SeatAlreadyTakenError(event_id=event.id)
            event.decrementSeats()

        # 2. RDS #2: 예매 기록 생성 (단일 DB 트랜잭션)
        async with self._reservation_session.begin():
            reservation = Reservation(
                user_id=user_id,
                event_id=payload.event_id,
                seat_no=payload.seat_no,
            )
            return await self._reservations.create(reservation)
```

### 규칙
- **트랜잭션은 `async with session.begin():` 으로** — 명시적 commit/rollback 금지
- **두 DB 에 걸친 단일 트랜잭션 시도 금지** — 위 예시처럼 순서대로 분리, 두 번째 실패 시 보상 로직
- **service 메서드는 키워드 인자 강제** (`*, user_id, payload`) — 호출 의도 명확화
- **return 타입은 ORM 모델 또는 도메인 객체** — Pydantic 변환은 router 책임

### 도메인 간 호출

```python
# 좋음: service 가 다른 도메인의 repository 를 주입받음
class ReservationService:
    def __init__(self, reservation_session, core_session):
        self._events = EventRepository(core_session)
```

```python
# 나쁨: service 가 다른 service 를 호출 (호출 그래프 폭발)
class ReservationService:
    def __init__(self, ...):
        self._event_service = EventService(...)  # 금지
```

> service 끼리의 호출은 순환 의존·트랜잭션 경계 모호 문제를 일으킨다. **도메인 간 협력은 repository 레벨에서만.**

## 트랜잭션 경계 · 동시성

### 좌석 예매 시 동시성

**문제**: 동일 좌석을 동시에 여러 사용자가 예매 시도

**해결책 1 — Row Lock (`SELECT ... FOR UPDATE`)**

```python
async def getForUpdate(self, event_id: int) -> Event | None:
    stmt = select(Event).where(Event.id == event_id).with_for_update()
    result = await self._session.execute(stmt)
    return result.scalar_one_or_none()
```

- 트랜잭션 안에서 `getForUpdate` 호출 → 해당 row 가 락에 걸려 다른 트랜잭션은 대기
- 좋은 점: 단순. PostgreSQL row lock 사용
- 주의: 데드락 가능성 → 항상 같은 순서로 lock (예: `event_id` 작은 것부터)

**해결책 2 — Unique Constraint + 재시도**

```python
# 좌석별 unique constraint
__table_args__ = (UniqueConstraint("event_id", "seat_no", name="uq_reservation_event_seat"),)
```

- 동시에 같은 좌석 INSERT 시도 → 하나만 성공, 나머지는 `IntegrityError`
- service 가 `IntegrityError` 잡아서 `SeatAlreadyTakenError` 로 변환
- 좋은 점: lock 경합 없음. 충돌 시에만 실패
- 권장: **예매 좌석 단위 경합은 이 방식**

```python
from sqlalchemy.exc import IntegrityError

try:
    reservation = await self._reservations.create(reservation)
except IntegrityError:
    raise SeatAlreadyTakenError(event_id=event.id, seat_no=payload.seat_no)
```

### 분산 lock — Redis (ElastiCache)
- 동일 사용자 중복 예매·결제 같은 비즈니스 lock 은 **Redis 분산 lock** 사용 (ElastiCache 가 이미 인프라에 있음)
- Python 인메모리 `asyncio.Lock` 사용 금지 (다중 EKS Pod 에서 무력화)

**좌석 hold 패턴** (스파이크 대응의 핵심):

```python
# app/common/redis_lock.py
from contextlib import asynccontextmanager
from redis.asyncio import Redis

@asynccontextmanager
async def seatHold(redis: Redis, event_id: int, seat_no: str, *, user_id: int, ttl_seconds: int = 300):
    """좌석 5분 hold. 결제 완료 시 release. TTL 만료 시 자동 해제."""
    key = f"seat:hold:{event_id}:{seat_no}"
    acquired = await redis.set(key, str(user_id), nx=True, ex=ttl_seconds)
    if not acquired:
        from app.common.errors import SeatAlreadyTakenError
        raise SeatAlreadyTakenError(event_id=event_id, seat_no=seat_no)
    try:
        yield
    except Exception:
        await redis.delete(key)
        raise
```

- **5분 TTL** — 결제 미완료 시 자동 release
- **SET NX EX** — 원자적 lock + 만료 (별도 unlock 필요 없음)
- **결제 성공 시** — DB 에 reservation 영구 기록 후 hold key 삭제

> Redis 사용 가이드 (커넥션 풀, key prefix, TTL 표준) 는 [08-aws-infrastructure.md](08-aws-infrastructure.md) 참조.

> **Idempotency Redis 캐시는 도입하지 않는다** — 결제 PG 미연동이라 핵심 경로의 중복 호출 위험이 낮고, 좌석 hold + 좌석 unique constraint 만으로 중복 예매를 차단할 수 있다.

## Alembic 마이그레이션

### 환경 분리

```
alembic/
├── core/                    # RDS #1
│   ├── alembic.ini
│   ├── env.py               # CoreBase.metadata 사용
│   └── versions/
└── reservation/             # RDS #2
    ├── alembic.ini
    ├── env.py               # ReservationBase.metadata 사용
    └── versions/
```

### 실행

```bash
# RDS #1
alembic -c alembic/core/alembic.ini upgrade head

# RDS #2
alembic -c alembic/reservation/alembic.ini upgrade head
```

### 작성 규칙
- **revision 메시지는 한국어 명사형** — `"users 테이블 추가"`, `"events.starts_at 인덱스 추가"`
- **autogenerate 결과는 수동 검토 후 commit** — 의도치 않은 drop/rename 감지
- **데이터 마이그레이션은 별도 revision** — 스키마 변경과 데이터 변경 분리
- **non-null 컬럼 추가는 3 단계** — ① nullable 추가 → ② 백필 → ③ NOT NULL 변경
- **인덱스는 `CREATE INDEX CONCURRENTLY`** (운영 DB) — 락 회피

```python
# 예: alembic/core/versions/20260601_xxxx_users_테이블_추가.py
def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_table("users")
```

## 비즈니스 검증

### 검증 위치 결정
- **형식 검증** (필수 필드, 길이, 타입) — Pydantic 스키마
- **비즈니스 규칙** (좌석 잔여, 결제 한도) — service 레이어
- **DB 제약** (unique, FK) — DB 레벨 + service 에서 IntegrityError 변환

### 도메인 예외 정의

```python
# app/common/errors.py — 발췌, 전체는 04-error-handling.md 참조
class DomainError(Exception):
    status_code: int = 500
    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


class SeatAlreadyTakenError(DomainError):
    status_code = 409
    code = "SEAT_ALREADY_TAKEN"

    def __init__(self, *, event_id: int, seat_no: str | None = None):
        super().__init__(
            "이미 선점된 좌석입니다",
            event_id=event_id,
            seat_no=seat_no,
        )
```

### 사용

```python
# service 안에서
if not event.hasAvailableSeats():
    raise SeatAlreadyTakenError(event_id=event.id)
```

- service 는 도메인 예외만 raise, HTTPException 으로 직접 변환하지 않는다
- 변환은 [04-error-handling.md](04-error-handling.md) 의 글로벌 예외 핸들러가 담당

## 결제 흐름 (Mock 기록)

> 본 시스템은 인프라 검증 베드이므로 **외부 PG 연동 없음**. `PaymentHistory` 는 예매 확정 시 단순 기록만 한다.

### 패턴

```python
# app/domains/payment/service.py
class PaymentService:
    def __init__(self, reservation_session: AsyncSession) -> None:
        self._payments = PaymentRepository(reservation_session)

    async def record(
        self,
        *,
        user_id: UUID,
        reservation_id: UUID,
        payment_method: str,
    ) -> PaymentHistory:
        """예매 확정과 함께 호출. 외부 PG 호출 없이 기록만."""
        history = PaymentHistory(
            user_id=user_id,
            reservation_id=reservation_id,
            payment_method=payment_method,
        )
        return await self._payments.create(history)
```

### 규칙
- **외부 호출 없음** — PG 어댑터·Mock 클래스 도입 X
- **상태 컬럼 추가 금지** — `pending/completed/failed` 같은 결제 상태 머신 불필요. 단순 기록
- **재시도 정책 없음** — 외부 시스템이 없으므로 재시도 대상이 없음
- **`ReservationService.confirm` 안에서 함께 호출** — 같은 RDS #2 트랜잭션 내 처리

```python
# 예매 확정 시 결제 기록 동반 (한 트랜잭션)
async with reservation_writer.begin():
    reservation = await reservations.confirm(reservation_id)
    await payments.record(
        user_id=reservation.user_id,
        reservation_id=reservation.id,
        payment_method="mock",
    )
```

## 안티 패턴

### 금지
- **service 끼리 import** — 호출 그래프 폭발
- **model 안에서 session 사용** — `self._session.add(...)` 같은 코드. repository 가 할 일
- **router 안에서 트랜잭션 시작** — service 책임 침범
- **repository 안에서 도메인 예외 raise** — repository 는 `None` 반환만
- **`session.commit()` 명시 호출** — `async with session.begin():` 만 사용
- **모든 repository 에 인터페이스 추가** — 테스트는 fixture 로, mock 은 unittest.mock 으로 충분
- **lazy loading 의존** — async 세션은 lazy 가 잘 동작하지 않음. 반드시 명시적 eager loading
- **N+1 무시** — 목록 조회 시 관계 객체 접근 전에 `selectinload` 적용
