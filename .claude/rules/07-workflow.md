# AI 작업 진행 규약

이 문서는 Claude · Copilot 등 AI 협업 도구가 본 프로젝트 (티켓팅 서비스 FastAPI) 에서 작업을 진행할 때 따라야 하는 **워크플로우 규약**입니다. 사용자 승인 요청을 빈번히 발생시켜 흐름이 끊기는 문제를 막고, AI 의 자율성과 안전성 사이 균형을 명문화합니다.

본 규약은 **무엇을 만드느냐**(아키텍처·코드 스타일·테스트) 가 아니라 **어떻게 진행하느냐**를 다룹니다. 코드 자체 규약은 [01-architecture.md](01-architecture.md) ~ [06-code-style.md](06-code-style.md) 참조.

> **간략화 우선** — 본 규약 자체도 본 프로젝트 규모에 맞춰 최소한입니다. "혹시 모르니" 의 예외 조항을 추가하지 않습니다.

## 핵심 6 규약

### 1. 이슈 먼저 (issue-first) 생성 정책

사용자 작업 지시가 도착하면 **코드 수정 시작 전에 GitHub 이슈를 먼저 생성**한다.

#### 원칙

- 모든 작업은 GitHub 이슈로 추적 — branch · commit · PR 모두 그 이슈를 참조
- **이슈 생성 시 카테고리 prefix 부여** — [app/README.md](../../README.md) 의 4 분류 (`[Feature]`, `[Refactor]`, `[Bug]`, `[Chore]`) 준수
- **규모가 PR 1 개로 reviewable diff 안 되면 메인 이슈 + sub-issue N 개로 분할**
  - 메인 이슈 본문에 전체 그림 + sub-issue 목록 + 완료 조건 명시
  - **GitHub 의 Sub-issue 기능 활용** — `gh api graphql` 의 `addSubIssue` mutation 으로 계층 명시
- 각 sub-issue 단위로 `branch → 작업 → commit → PR` 사이클 반복
- PR closing reference 는 그 sub-issue (`Closes #<sub>`). 메인 이슈는 모든 sub-issue close 시 함께 close

#### Why
- 작업 진입 전 사용자와 scope 합의 강제 → 작업 도중 방향 이탈 회피
- ad-hoc 으로 PR 직전 이슈를 만드는 패턴 차단
- 메인 ↔ sub-issue 의 계층 관계 GitHub 상 명확화

#### 예외
- 사용자가 명시적으로 **"이슈 없이 진행해"** / **"단발 hotfix"** 라고 지시한 경우
- 1 줄 typo · 명백한 작은 chore — 단, PR 타이틀 컨벤션 충족 위해 작업 시작 전 이슈 생성 권장

#### 판단 모호 시
규모가 작아 보여도 **이슈 1 개 생성**. 작업 끝난 후 PR 정리할 때 추가 비용 거의 없음.
"이거 큰가?" 가 50/50 이면 **메인 + sub-issue 분할 쪽**으로 보수 분류.

#### Sub-issue 등록 명령

```bash
# 메인 이슈에 sub-issue 등록 (Relation 자동 활성화)
MAIN_ID=$(gh issue view <MAIN_NUMBER> --json id --jq .id)
SUB_ID=$(gh issue view <SUB_NUMBER> --json id --jq .id)

gh api graphql -f query='
mutation($issueId: ID!, $subIssueId: ID!) {
  addSubIssue(input: {issueId: $issueId, subIssueId: $subIssueId}) {
    issue { number }
    subIssue { number }
  }
}' -f issueId="$MAIN_ID" -f subIssueId="$SUB_ID"
```

<br>

### 2. 자율 진행 정책 — 승인 요청 최소화

쿼리의 의도가 명확하면 AI 는 **사용자 승인 없이 진행**한다.

> **핵심 원칙 1**: 아래 "자율 진행 영역" 에 해당하는 작업은 **절대 사용자 확인을 요청하지 않는다.**
> 스크립트 실행, 파일 수정, 커밋, 브랜치 생성 등은 묻지 않고 즉시 실행한다.
> 이미 허용된 도구 (`Bash`, `Edit`, `Write`, `gh`, `git`, `pytest`, `ruff`, `alembic` 등) 는 추가 승인 없이 사용한다.
>
> **핵심 원칙 2**: 최대한 자율적으로 진행하되, "예외 영역" 에 해당하는 작업은 반드시 사용자 확인을 받는다.

다음 4 가지 영역만 예외로 사용자 확인을 받는다.

#### 예외 영역 (반드시 사용자 확인)

| 영역 | 예시 |
|---|---|
| **시스템 자체 변경** | OS · 패키지 · 글로벌 환경 변경 (`apt-get install`, `sudo systemctl`, 시스템 서비스 enable 등) |
| **언급 없는 destructive 권한** | `git push --force`, branch 삭제, DB `DROP TABLE`, `git reset --hard`, alembic `downgrade`, 무인 PR merge |
| **AWS / 인프라 변경** | `terraform apply`, `kubectl apply`, ECR push, EKS rollout, RDS / SQS / Lambda / IAM 직접 변경 — **반드시 plan 출력 + 사용자 확인** |
| **외부 시스템 영향** | PR merge · issue close · 배포 트리거 · 외부 API 비용 결제 (PG 실거래 호출) · 외부 DM 발송 · CloudWatch 알람 토글 |
| **모호한 작업 범위** | 사용자 의도가 다중 해석 가능 · scope 불명확 — 진행 전 구체화 질문 |

#### 자율 진행 영역 (승인 불필요 — 즉시 실행)

- 코드 작성 · 수정 · 리팩토링 · 삭제
- 테스트 추가 · 갱신
- 새 파일 · 디렉토리 생성
- DB migration 작성 (`alembic revision`) — 단 `DROP` 류는 예외 (위 destructive 영역)
- 의존성 추가 (`pip install`, `pyproject.toml` 수정) — 단 신규 외부 패키지는 규약 5 적용
- Branch 생성, 정상 push (force-push 아닌)
- Commit 단위 결정 및 실행
- PR 본문 작성
- `scripts/` 하위 스크립트 실행 — 프로젝트 도구는 경로 확인 없이 실행
- 이슈 · PR Label 부여
- lint · fmt · test · type check 실행 (`ruff`, `black`, `mypy`, `pytest`)
- **Terraform `plan` 실행 (변경 없음, 미리보기 전용)**
- **k8s manifest 작성 · 수정** (`deploy/` 하위)
- **Dockerfile 작성 · 빌드 검증** (push 는 자율 영역 X)
- **부하 테스트 시나리오 작성** (`loadtest/` 하위) — 실행은 staging 한정

#### 판단 모호 시
"이게 destructive 영역인가?" 가 50/50 이면 **사용자 확인 쪽으로 보수 분류**. 단, 이미 자율 진행 영역으로 열거된 항목은 50/50 이 아니다 — 확인 없이 진행한다.

<br>

### 3. Commit-per-TODO 정책

별다른 사용자 언급이 없으면, AI 는 작업을 **논리적 변경 단위 (TODO)** 마다 commit 한다.

> **금지**: 작업을 모두 완료한 뒤 한 번에 몰아서 커밋하는 것은 **절대 허용하지 않는다.**
> 논리적 변경 단위가 완성되는 즉시 커밋한다. 커밋을 뒤로 미루지 않는다.

#### 원칙

- 논리적 변경 단위 완성 → **즉시 커밋** (다음 단위 작업 시작 전)
- 큰 PR 도 reviewable diff 단위로 분할 commit
- 각 commit 메시지는 [06-code-style.md](06-code-style.md) 의 컨벤션 준수:
  - **prefix 는 네 가지 중 택 1**: `[FEAT]:` / `[FIX]:` / `[REFAC]:` / `[CHORE]:`
  - 이후 한국어 + 변경 의도
  - 단일 commit 이 너무 큰 변경을 담지 않도록
- 빌드 그린 유지 — 각 commit 이 lint · type · test 통과 가능한 상태

#### 잘못된 패턴 (금지)

```text
# BAD — 작업 완료 후 모아서 한 번에 커밋
[모델 작성] → [스키마 작성] → [서비스 작성] → [라우터 작성] → [테스트 작성] → 커밋 하나로 묶음
```

#### 올바른 패턴

```text
# GOOD — 논리 단위마다 즉시 커밋
[Reservation 모델 + Alembic revision] → 커밋
[Reservation Pydantic 스키마] → 커밋
[Reservation repository + service.create] → 커밋
[Reservation router 등록 + 인증 wiring] → 커밋
[Reservation 통합 테스트] → 커밋
```

#### 예외
- 사용자가 명시적으로 **"한 번에 묶어줘"** / **"squash 해줘"** 요청 시 단일 commit
- 사용자가 **"단일 fix 만 해줘"** 등 명백한 단일 변경을 지시한 경우

#### 예시

```
[FEAT]: Reservation 모델 + Alembic 마이그레이션 추가
[FEAT]: ReservationCreate · ReservationRead 스키마 정의
[FEAT]: ReservationService.create — 좌석 FOR UPDATE 락 + 도메인 예외
[FEAT]: /reservations POST 라우터 + 인증 의존성 wiring
[FEAT]: 예매 동시성 통합 테스트 추가
```

<br>

### 4. PR 자동 생성 정책

작업 완료 직후 (별다른 언급 없으면) AI 는 **PR 을 자동 생성**한다.

#### 컨벤션 준수

- **PR 타이틀**: `[카테고리#이슈번호] 제목` 형식 ([06-code-style.md](06-code-style.md) 참조)
- **본문**: `.github/PULL_REQUEST_TEMPLATE.md` 의 모든 섹션 채움 (없으면 본 룰셋의 기본 템플릿 적용)
- **이슈 링크**: PR 본문 또는 Development sidebar 에 `Closes #N`
- **Label 부여**: 규약 6 의 매핑에 따라 PR 에도 동일 label 부여

#### 기본 PR 템플릿

저장소에 PULL_REQUEST_TEMPLATE.md 가 없을 때 본 형식 사용:

```markdown
## 연관 이슈
Closes #<번호>

## 구현 내용
- 변경 요점 1
- 변경 요점 2

## 변경 영향 범위
- 영향을 받는 도메인·라우터·DB

## 테스트
- [ ] 단위 테스트 통과
- [ ] 통합 테스트 통과
- [ ] 수동 확인 시나리오: ...

## 롤백 계획
- 마이그레이션 downgrade 절차 · 환경 변수 원복 등
```

#### 예외

- 작업이 이슈와 무관한 단발성 chore — 사용자가 "이슈 없이 PR 올려줘" 또는 "이슈 먼저 만들어줘" 명시
- 작업이 PR 단위가 아닌 운영 명령 (예: migration 적용, log 분석) 만 요청한 경우

<br>

### 5. 권한 · 의존성 최소화

자율 진행 시, **꼭 필요한 경우가 아니면 이미 허용된 권한 범위 내에서만 동작**한다.

#### 원칙

- 새 `Bash(...)` permission 요청은 작업 완수에 불가피할 때만
- 동등 효과를 낼 수 있는 기존 허용 도구가 있으면 그것을 우선 — 기존 `gh` · `git` · `pip` · `pytest` · `alembic` · `ruff` · `mypy` 활용
- **신규 외부 의존성 추가**(`pyproject.toml`) 는 **본 규약의 "모호 영역"** 으로 간주 → 사용자 사전 확인
  - 단, 이미 룰셋에 명시된 의존성 (`fastapi`, `sqlalchemy`, `asyncpg`, `pydantic`, `pyjwt`, `passlib`, `structlog`, `tenacity`, `pytest-asyncio` 등) 추가는 자율 진행
- `WebFetch` · `WebSearch` 도 새 도메인은 작업 명시적 필요 시에만

#### 이유
- 누적 권한이 늘어날수록 `.claude/settings.local.json` 의 entries 비대화
- 잘못된 도구 도입은 보안 노출 위험 (토큰 노출, 시스템 파괴 명령 등)

#### 패키지 선택 보수 원칙
- **이미 룰셋에 있는 라이브러리로 가능하면 그것 사용**
- 새 패키지가 정말 필요한 경우, 다음을 함께 보고:
  - 왜 기존 패키지로 안 되는지
  - 유지보수 활성도 (최근 release · stars)
  - 라이선스
  - 의존성 트리 크기

<br>

### 6. 이슈 · PR 분류 메타데이터 정책 — Label

이슈 · PR 생성 시 **항상 Label 부여**.

#### 카테고리 prefix 체계 (commit / PR / 이슈)

본 repo 는 commit · PR · 이슈 제목의 prefix 를 의도적으로 다른 표기로 운용한다.

| 위치 | 형식 | 예시 |
|---|---|---|
| Commit message | `[FEAT]:` / `[FIX]:` / `[REFAC]:` / `[CHORE]:` (대문자 축약 + 콜론) | `[FIX]: 좌석 락 누락 보정` |
| PR title | `[FEAT#N]` / `[FIX#N]` / `[REFAC#N]` / `[CHORE#N]` (commit 카테고리 + #이슈번호, 콜론 없음) | `[FEAT#15] 예매 생성 API` |
| Issue title | `[Feature]` / `[Refactor]` / `[Bug]` / `[Chore]` (full-word, 콜론 없음, app/README.md 컨벤션) | `[Feature] 예매 생성 API + 좌석 락` |

#### Label 매핑 (이슈 prefix 기준)

| Issue prefix | Label |
|---|---|
| `[Feature]` | `enhancement` |
| `[Refactor]` | `refactor` |
| `[Bug]` | `bug` |
| `[Chore]` | `chore` |

PR 의 Label 은 그 PR 이 닫는 이슈 (`Closes #N`) 의 Label 과 동일하게 부여한다.

#### 부여 명령 예시

**이슈 생성 + Label 부여**

```bash
gh issue create \
  --title "[Feature] 예매 생성 API + 좌석 동시성 락" \
  --label enhancement \
  --body "..."
```

**PR 생성 + Label 부여**

```bash
gh pr create \
  --title "[FEAT#15] 예매 생성 API + 좌석 동시성 락" \
  --label enhancement \
  --body "$(cat <<'EOF'
## 연관 이슈
Closes #15

## 구현 내용
- Reservation 모델 추가
- ReservationService.create 좌석 락 적용
- 라우터 + 인증 wiring
- 동시성 테스트

## 변경 영향 범위
- RDS #2 (reservation DB) 스키마 추가
- /reservations 신규 엔드포인트

## 테스트
- [x] 단위 테스트
- [x] 통합 테스트 (동시성 포함)

## 롤백 계획
- alembic downgrade -1 (reservation env)
EOF
)"
```

#### Why
- Label 누락 시 GitHub Issues · PR 필터링 무력화
- 카테고리 통계가 의미 있게 누적되려면 일관 부여 필요

#### How to apply
- 이슈 생성 직후 Label 부여 — 까먹지 않도록 같은 회차에서 처리
- PR 생성 직후 Label 부여 — 닫는 이슈의 Label 과 자동 동기화
- 매핑이 모호하면 가장 큰 변경 의도 prefix 기준으로 분류

<br>

## 적용 흐름 (요약)

사용자 요청 도착 →

1. **의도가 명확한가?** Yes → 진행 / No → 구체화 질문 (규약 2 의 모호 영역)
2. **이슈 생성 + Label 부여** (규약 1 + 규약 6) — 단발은 이슈 1 개 / 큰 작업은 메인 + sub-issue N 개로 분할 후 모두 사전 생성. "이슈 없이 진행해" 명시 시 skip
3. **destructive / 시스템 / 외부 영향?** Yes → 사용자 확인 / No → 진행
4. **새 권한 / 외부 의존성 필요?** Yes → 사용자 확인 / No → 진행 (규약 5)
5. **작업 진행** — sub-issue 단위로 branch · 논리 단위마다 commit (규약 3)
6. **작업 완료 → PR 자동 생성 + Label 부여** (규약 4 + 규약 6) — `Closes #<sub-issue>` 명시

<br>

## 참고 자료

- 본 프로젝트 컨벤션: [app/README.md](../../README.md)
- 관련 규약:
  - [06-code-style.md](06-code-style.md) — commit · PR 메시지 컨벤션
  - [05-testing.md](05-testing.md) — 작업 단위 테스트 기준
- 관련 문서:
  - `.github/PULL_REQUEST_TEMPLATE.md` (저장소 도입 후)
  - `.github/ISSUE_TEMPLATE/` (저장소 도입 후)

<br>

## 본 룰셋 사용 시 AI 에게 주의 사항

본 룰셋은 **간략화된 학습·실습 규모의 티켓팅 서비스** 를 전제로 한다. AI 는 다음을 항상 염두에 둔다.

- "엔터프라이즈급으로 짜줘" 류 요청을 받아도 [README.md 의 "간략화 원칙"](README.md#프로젝트-성격--간략화-원칙-필독) 을 우선 적용
- 새 추상 레이어·인터페이스·디자인 패턴은 **실제 분기 2개 이상 발생 시점**에 도입
- 두 RDS 에 걸친 atomic 트랜잭션 같은 분산 트랜잭션 패턴은 도입 금지 — 도메인 이벤트 또는 보상 트랜잭션
- 룰셋 자체에 적힌 내용도 의심스러우면 더 단순한 쪽으로 — 룰 충돌 시 간략화 원칙 우선
