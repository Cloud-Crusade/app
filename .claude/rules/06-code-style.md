# 코드 스타일 · 컨벤션

## 핵심 원칙

> **간략화 우선** — 코드는 자신을 설명한다. 장황한 docstring·과한 주석·불필요한 추상화는 가독성을 해친다. 본 룰셋의 모든 규칙은 "팀이 빠르게 읽고 이해할 수 있는 코드" 를 위한 것이다.

### 핵심 가치
- **읽기 쉬움 우선** — 영리한 코드보다 명확한 코드
- **자가 설명** — 네이밍으로 의도 표현
- **최소한** — 필요 없으면 안 쓴다 (코드도, 주석도, 추상화도)

## Python 포맷팅

### 도구

| 도구 | 역할 |
|---|---|
| **ruff** | linter + formatter + import 정렬 |
| **black** | 포맷터 (ruff format 으로 대체 가능) |
| **mypy** | 정적 타입 검사 |

### pyproject.toml 설정 (권장)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # comprehensions
    "UP",   # pyupgrade
    "N",    # pep8-naming (필요 시 일부 해제)
    "T20",  # no print
    "SIM",  # simplify
    "RUF",  # ruff-specific
]
ignore = [
    "N802",  # function name `getUser` 같은 camelCase 허용 (프로젝트 네이밍 규약)
    "N803",  # argument name 도 동일
    "N806",  # variable in function 도 동일
]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_ignores = true
plugins = ["pydantic.mypy"]
```

### 규칙
- **들여쓰기**: 스페이스 4 (PEP 8)
- **줄 길이**: 최대 100자
- **따옴표**: 큰따옴표 통일
- **import 정렬**: ruff (`I` 룰) 가 자동

## import 순서

```python
# 1. 표준 라이브러리
from collections.abc import AsyncIterator
from datetime import datetime

# 2. 외부 라이브러리
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# 3. 프로젝트 내부
from app.common.deps import getCurrentUser
from app.domains.user.model import User
```

- ruff `I` 룰이 자동 처리. 수동 정렬 금지

## 타입 힌트

### 필수 영역
- **모든 함수 시그니처** — 매개변수와 반환값
- **모든 클래스 속성** — `Mapped[...]`, `BaseModel` 필드
- **공개 모듈 변수**

```python
# 좋음
async def getUser(user_id: int, session: AsyncSession) -> User | None:
    return await session.get(User, user_id)


# 나쁨 — 타입 정보 누락
async def getUser(user_id, session):
    return await session.get(User, user_id)
```

### 현대 표기법 (Python 3.10+)
- **Union 은 `X | Y`** — `typing.Union` 사용 안 함
- **Optional 은 `X | None`** — `typing.Optional` 사용 안 함
- **Generic 은 빌트인** — `list[str]`, `dict[str, int]` (`List`, `Dict` X)

```python
# 좋음
def parse(items: list[str]) -> dict[str, int] | None: ...

# 나쁨 (legacy)
from typing import List, Dict, Optional
def parse(items: List[str]) -> Optional[Dict[str, int]]: ...
```

### `Any` 회피
- **외부 라이브러리 경계** 외에는 사용 금지
- 어쩔 수 없으면 `# type: ignore[reason]` 주석으로 이유 명시

## 네이밍 규약

> 본 프로젝트는 **app/README.md 의 네이밍 규약**을 따른다.

### Class — PascalCase

```python
class User: ...
class ReservationService: ...
class PaymentGatewayClient: ...
```

- 명사 단수형
- 의미가 즉시 드러나도록 — `Manager`, `Handler` 같은 모호한 suffix 자제

### Method — camelCase

```python
class UserService:
    async def getUser(self, user_id: int) -> User: ...          # public
    async def createUser(self, payload: UserCreate) -> User: ...  # public
    def _hashPassword(self, raw: str) -> str: ...                # private
```

- **public**: 일반 문자로 시작 (`getUser`)
- **private**: 언더바로 시작 (`_hashPassword`)
- **REST 액션이 아닌 의도 기준** — `find`, `lookup`, `dispatch` 같이 동작을 묘사
- **`get/create/update/delete` 외 자유** — `dispatch`, `cancel`, `confirm`, `charge` 등

> ⚠️ PEP 8 표준은 snake_case 이지만, 본 프로젝트는 팀 컨벤션상 메서드를 camelCase 로 작성한다. ruff 의 `N802`, `N803`, `N806` 룰을 ignore 한다.

### Variable — snake_case

```python
user = User(...)
event_id = 42
available_seats = event.total_seats - reserved_count
```

- 모든 지역 변수, 함수 매개변수, 클래스 속성
- **무의미한 이름 금지** — `data`, `item`, `tmp`, `obj`, `result1`, `data2`
- **루프 변수는 짧아도 됨** — `for r in reservations:` OK. 단 의미가 모호하면 풀이

### Module / File — snake_case

```
domains/user/model.py
common/deps.py
routers/reservations.py
```

### 함수 vs 메서드
- **모듈 레벨 함수**: snake_case 도 허용 — 외부 라이브러리 컨벤션을 따를 때 (FastAPI 의존성·예외 핸들러 등)
- 가능하면 camelCase 로 통일

```python
# common/deps.py
async def getCurrentUser(...) -> User: ...  # 권장
```

### 상수

```python
JWT_ALGORITHM = "HS256"
MAX_PAGE_SIZE = 100
```

- UPPER_SNAKE_CASE
- 모듈 최상단에 배치

## 함수 설계

### 작은 함수
- **30 줄 이내** 권장 (60 줄 초과 시 분해 검토)
- **한 가지 책임** — 분기·로직이 늘면 추출

### 매개변수
- **5 개 이하** — 초과 시 Pydantic 모델로 묶기

```python
# 좋음
async def createReservation(
    self, *, payload: ReservationCreate, user_id: int,
) -> Reservation: ...

# 나쁨
async def createReservation(
    self, user_id, event_id, seat_no, ticket_count, payment_method, coupon_code,
): ...
```

### 키워드 전용 인자
- service 메서드, repository 메서드는 **`*` 로 키워드 강제** — 호출 의도 명확

```python
async def create(self, *, user_id: int, payload: ReservationCreate) -> Reservation: ...

# 호출 시 의도 명확
await service.create(user_id=1, payload=payload)
```

### 조기 반환

```python
# 좋음
def validate(user: User) -> None:
    if not user.email:
        raise InvalidEmailError()
    if user.is_suspended:
        raise SuspendedUserError()
    # ... 본 로직


# 나쁨 — 깊은 중첩
def validate(user: User) -> None:
    if user.email:
        if not user.is_suspended:
            # ... 본 로직
        else:
            raise SuspendedUserError()
    else:
        raise InvalidEmailError()
```

## 비동기 코드

### 기본 규칙
- **I/O 경계는 모두 `async def`** — DB, HTTP, 캐시
- **동기 함수 안에서 비동기 호출 금지** — `asyncio.run()` 으로 강제 실행 X
- **`await` 누락 검사** — ruff 가 잡지만 mypy strict 도 같이 보기

### 비동기 컨텍스트 매니저

```python
# 좋음
async with session.begin():
    await repo.create(obj)

# 나쁨
session.begin()
await repo.create(obj)
session.commit()
```

### `asyncio.gather` vs 직렬

```python
# 독립적인 두 호출 — 병렬
event, user = await asyncio.gather(
    eventRepo.getById(event_id),
    userRepo.getById(user_id),
)

# 의존성이 있으면 직렬 (gather 사용 금지)
event = await eventRepo.getById(event_id)
seats = await seatRepo.getByEvent(event.id)
```

### CPU bound 작업
- **`run_in_executor`** 또는 `loop.run_in_executor` 명시 사용
- async 함수 안에서 무거운 CPU 작업 직접 실행 시 이벤트 루프 블로킹

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)

async def hashPassword(raw: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, _bcryptHash, raw)
```

## Pydantic 모델

### v2 스타일

```python
from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=72)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime
```

### 규칙
- **`from_attributes=True`** — ORM 객체 직접 변환
- **`Field()` 로 제약** — 길이·범위·정규식
- **`model_validate(orm_obj)`** 사용, `from_orm` (deprecated) 금지
- **`validator` 데코레이터는 `field_validator` 사용** (v2)
- **공통 필드는 베이스 분리**, 상속은 1 단계까지만

### 응답 모델 분리

```python
# 좋음
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: int
```

- 요청과 응답은 분리 (응답에 password 노출 차단)

## SQLAlchemy 2.0 스타일

### 모델 정의

```python
from sqlalchemy.orm import Mapped, mapped_column

class User(CoreBase, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
```

- `Mapped[...]` + `mapped_column(...)` 형식 (legacy `Column(...)` 금지)
- 타입은 Python 표기 (`Mapped[int]`, `Mapped[str | None]`)

### 쿼리

```python
from sqlalchemy import select

# 좋음 — 2.0 스타일
stmt = select(User).where(User.email == email)
result = await session.execute(stmt)
user = result.scalar_one_or_none()

# 나쁨 — 1.x legacy
user = session.query(User).filter_by(email=email).first()  # 금지
```

## 주석 정책

### 언어
- **한국어 단일** — 코드 주석, 함수 설명, 마이그레이션 메시지, 커밋, 로그 이벤트 외 메시지 모두 한국어
- **예외**: 변수/함수/이벤트 이름, ASCII 식별자, 외부 라이브러리 인용

### 작성 원칙
- **WHY 만 적는다** — WHAT 은 코드가 말한다
- **자명한 주석 금지** — `# i 를 1 증가` 같은 것
- **삭제된 코드 주석으로 남기지 않음** — 버전 관리가 한다

```python
# 좋음
def applyBackoff(attempt: int) -> float:
    # 클라이언트 폭주 방지를 위해 jitter 추가 — full jitter (AWS Architecture Blog 패턴)
    return random.uniform(0, min(MAX_DELAY, BASE_DELAY * 2 ** attempt))

# 나쁨
def applyBackoff(attempt: int) -> float:
    # backoff 시간 계산
    return random.uniform(0, min(MAX_DELAY, BASE_DELAY * 2 ** attempt))
```

### docstring
- **함수 docstring 은 기본 작성 X** — 함수 이름이 의도를 말한다
- **공개 패키지 API · 비자명한 알고리즘에만 작성**
- 형식: 한 줄 요약. 멀티 라인 docstring 자제 (Sphinx 도입 전까지 불필요)

```python
# 적절
def issueAccessToken(user_id: int) -> str:
    """access token 발급. exp=30분."""
    ...

# 과함
def issueAccessToken(user_id: int) -> str:
    """
    Issues an access token for the given user_id.

    Args:
        user_id: The ID of the user to issue the token for.

    Returns:
        A signed JWT string.

    Raises:
        ValueError: If user_id is invalid.

    Example:
        >>> issueAccessToken(1)
        'eyJhbGc...'
    """
    ...
```

> 두 번째 예시 같은 docstring 은 **금지**. 한 줄로 충분하다.

### TODO 주석

```python
# TODO(juhy): PG 콜백 idempotency_key 검증 추가 (이슈 #42)
```

- **작성자 + 이유 + 이슈 번호** 명시
- 맥락 없는 `# TODO: fix this` 금지

## 클래스 설계

### 필드 순서

```python
class Event(CoreBase, TimestampMixin):
    __tablename__ = "events"

    # 식별
    id: Mapped[int] = mapped_column(primary_key=True)

    # 컨텐츠
    title: Mapped[str] = mapped_column(String(200))
    venue: Mapped[str] = mapped_column(String(200))

    # 상태
    available_seats: Mapped[int] = mapped_column(Integer)
    total_seats: Mapped[int] = mapped_column(Integer)

    # 일정
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

### 상속·믹스인
- **`TimestampMixin` 같은 작은 mixin 만 허용** — 깊은 상속 트리 금지
- **추상 베이스 클래스 (`ABC`) 도입 신중** — 구현체 1개면 안 만든다

## SQL 스타일 (raw query 작성 시)

대부분 SQLAlchemy 로 충분하지만 raw query 가 필요할 때:

```python
from sqlalchemy import text

stmt = text("""
    SELECT
        u.id,
        u.email,
        COUNT(r.id) AS reservation_count
    FROM users u
    LEFT JOIN reservations r ON r.user_id = u.id
    WHERE u.created_at > :since
    GROUP BY u.id, u.email
    ORDER BY reservation_count DESC
    LIMIT :limit
""")
```

- **키워드 대문자**, **테이블·컬럼 snake_case**
- **2 칸 들여쓰기**, **컬럼은 한 줄 한 개**
- **파라미터 바인딩** (`:since`) — f-string 으로 값 삽입 절대 금지 (SQL injection)

## YAML 스타일

```yaml
# 좋음
database:
  core:
    host: rds-core.internal
    port: 5432
    pool_size: 10
  reservation:
    host: rds-reservation.internal
    port: 5432
    pool_size: 20

jwt:
  algorithm: HS256
  access_ttl_seconds: 1800   # 30 분
```

- 2 칸 들여쓰기
- 키는 snake_case
- 비자명한 값에만 주석

## 안티 패턴

### 1. 매직 넘버

```python
# 나쁨
if attempt > 3:
    raise ...

# 좋음
MAX_RETRIES = 3
if attempt > MAX_RETRIES:
    raise ...
```

### 2. 깊은 중첩

```python
# 나쁨
if user:
    if user.active:
        if user.email:
            send(user.email)

# 좋음
if user is None or not user.active or not user.email:
    return
send(user.email)
```

### 3. else after return

```python
# 나쁨
if err:
    return err
else:
    process()

# 좋음
if err:
    return err
process()
```

### 4. 무의미한 임시 변수

```python
# 나쁨
def isValid(s: str) -> bool:
    result = len(s) > 0
    return result

# 좋음
def isValid(s: str) -> bool:
    return len(s) > 0
```

### 5. 광범위한 `except Exception`

```python
# 나쁨
try:
    ...
except Exception:
    pass

# 좋음 — 특정 예외만 의도적으로
try:
    ...
except IntegrityError as exc:
    raise SeatAlreadyTakenError(...) from exc
```

### 6. 모듈 import 시 부수효과

```python
# 나쁨 — import 만 해도 DB 연결
engine = create_async_engine(settings.core_db_url)  # 모듈 최상단

# 좋음 — factory 함수
def buildCoreEngine() -> AsyncEngine:
    return create_async_engine(settings.core_db_url)
```

### 7. `print()` 디버깅 잔존
- ruff `T20` 룰로 차단
- 로그는 `structlog.get_logger().info(...)`

### 8. `# noqa` 남발
- 정당한 이유 없이 `# noqa` 금지
- 사용 시 `# noqa: E501  # 긴 URL 이라 분할 어려움` 처럼 이유 명시

## Git 컨벤션

> 본 프로젝트는 **app/README.md 의 컨벤션**을 따른다. 본 섹션은 그 컨벤션을 코드 룰셋 안에 다시 한 번 명문화한 것이다.

### 커밋 메시지

```
[카테고리]: 변경 내용
```

| 카테고리 | 의미 |
|---|---|
| `[FEAT]` | 기능 추가·변경 |
| `[FIX]` | 버그·오류 수정 |
| `[REFAC]` | 리팩토링·구조 변경 |
| `[CHORE]` | 의존성 추가, 코드 외 작업 (문서·설정) |

#### 규칙
- **메시지는 한국어 단일** — 한국어 단일 정책 (본 룰셋 전반)
- **명사형 종결** — `구현`, `수정`, `추가`
- **카테고리는 위 4 가지만** — 임의 추가 금지

#### 예시

```
[FEAT]: 예매 생성 API + 좌석 동시성 락 구현

- ReservationService.create 에 SELECT FOR UPDATE 적용
- SeatAlreadyTakenError 도메인 예외 추가
- 동시 요청 테스트 추가
```

```
[FIX]: JWT 검증 시 만료 토큰을 401 로 반환

- decodeAccessToken 의 ExpiredSignatureError 처리 누락 보정
- 관련 테스트 케이스 추가
```

```
[REFAC]: Reservation repository 의 쿼리 단순화

- 중복된 페이지네이션 코드 통합
- 의존성 방향 정리 (model → repository 역참조 제거)
```

```
[CHORE]: tenacity 의존성 추가 + 결제 PG 재시도 wiring
```

### 브랜치 이름

```
카테고리/#이슈번호/브랜치명
```

| 카테고리 | 대응 커밋 |
|---|---|
| `feature/` | `[FEAT]` |
| `fix/` | `[FIX]` |
| `refactor/` | `[REFAC]` |
| `chore/` | `[CHORE]` |

#### 규칙
- **브랜치명은 영문 소문자 + 하이픈**, 30 자 이내
- **변경 핵심 대상**을 표현 — 파일·모듈명 기준

#### 예시

```
feature/#15/reservation-create-api
feature/#16/jwt-auth
fix/#21/seat-race-condition
refactor/#30/payment-service-split
chore/#33/ruff-config
```

### Pull Request

```
[카테고리#이슈번호] PR 제목
```

- 카테고리는 커밋과 동일 (`FEAT`, `FIX`, `REFAC`, `CHORE`)
- 제목은 한국어, 70 자 이내
- 본문은 PR 템플릿 준수 ([07-workflow.md](07-workflow.md) 참조)

#### 예시

```
[FEAT#15] 예매 생성 API + 좌석 동시성 락
[FIX#21] 좌석 race condition 보정 (FOR UPDATE 적용)
[REFAC#30] PaymentService 분할 — 재시도 로직 외부 어댑터로 이동
```

## 파일 구조 (Python 파일)

```python
"""모듈 한 줄 요약 (선택)."""

# 1. 표준 import
from datetime import datetime

# 2. 외부 import
from sqlalchemy.ext.asyncio import AsyncSession

# 3. 내부 import
from app.common.errors import DomainError

# 4. 상수
MAX_RETRIES = 3

# 5. 타입·자료구조
class TokenPayload(BaseModel):
    user_id: int

# 6. 공개 함수·클래스
class UserService:
    ...

# 7. private 헬퍼
def _hashPassword(raw: str) -> str:
    ...
```

## 코드 리뷰 체크리스트

PR 제출 전 확인:

- [ ] 주석으로 남긴 코드 없음
- [ ] 매직 넘버 없음
- [ ] 모든 함수 시그니처에 타입 힌트
- [ ] 예외 처리 누락 없음
- [ ] 함수 30 줄 이내 (예외 가능)
- [ ] 중첩 4 단계 이하
- [ ] 테스트 추가됨 ([05-testing.md](05-testing.md))
- [ ] 로그 구조화 필드 사용
- [ ] 주석이 WHY 만 설명
- [ ] 사용 안 하는 import·변수 없음
- [ ] private 메서드 (`_xxx`) 외부 호출 없음
- [ ] async 함수 안 동기 I/O 없음
- [ ] 응답 모델에 민감 필드 노출 안 됨
- [ ] DB 트랜잭션 경계 명확 (service 안 `async with session.begin():`)
- [ ] 두 RDS 에 걸친 atomic 트랜잭션 없음
