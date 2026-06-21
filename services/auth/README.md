# auth 서비스

## 개요

회원가입·로그인·JWT(access/refresh) 발급·갱신을 담당하는 FastAPI 서비스다. `user` 테이블의 **소유 서비스**로 RDS#1(core) 에 속하며, gRPC 는 제공도 호출도 하지 않는다. 다른 서비스의 인증은 토큰의 `user_id` 만으로 완결되므로 본 서비스가 전체 인증의 기반이 된다.

## 도메인 · 엔드포인트

도메인 `user` — `User`: `user_id` UUID PK, `user_name` String(255) unique, `password_hash`(bcrypt), `created_at`.

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/auth/signup` | - | 가입. `IntegrityError`→`DuplicateUserNameError`(409). writer |
| POST | `/auth/login` | - | 비밀번호 검증 후 `TokenPair` 발급. reader |
| POST | `/auth/refresh` | - | refresh 토큰만으로 토큰쌍 재발급. **DB 미조회** |
| GET | `/users/me` | ✓ | 토큰의 user_id 로 단건 조회. reader |
| GET | `/healthz`·`/readyz` | - | liveness / readiness(core DB `SELECT 1`) |

## 핵심 동작

- **stateless refresh** — `decodeToken(refresh_token, expected_type="refresh")` 로 유효성만 확인하고 user_id 를 추출해 즉시 access/refresh 를 재발급한다. DB·캐시 조회가 없다.
- **가입 중복 차단** — `user_name` unique 제약에 의존. service 가 `async with session.begin()` 안에서 `IntegrityError` 를 잡아 도메인 예외로 변환.
- **비밀번호** — `hashPassword`/`verifyPassword`(bcrypt). 평문·해시 모두 로깅·응답 노출 금지.

## 의존

- **DB** — RDS#1(core) writer/reader. `DB_WRITER_URL`/`DB_READER_URL`. 가입만 writer, 나머지는 reader.
- **gRPC / SQS / Redis** — 없음.
- **libs** — `common`(`app_factory`·`security`·`db`·`errors`·`auth`), `config.settings`.

---
⬆ [services README로](../README.md)
