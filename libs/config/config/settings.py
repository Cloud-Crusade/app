from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"

    # 프론트엔드(cc/web) 교차 출처 요청 허용 origin — preflight(OPTIONS) 처리
    cors_allow_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        alias="CORS_ALLOW_ORIGINS",
    )

    # 서비스별 DB 연결 — 각 서비스가 자기 롤로 자기 테이블만 접근 (물리 DB 공유, GRANT 는 cc/infra).
    # 값은 서비스 배포 env 가 주입 (auth/event→RDS#1 role, reservation/payment→RDS#2 role)
    db_writer_url: str = Field(..., alias="DB_WRITER_URL")
    db_reader_url: str = Field(..., alias="DB_READER_URL")

    redis_url: str = Field(..., alias="REDIS_URL")

    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_seconds: int = Field(default=1800, alias="JWT_ACCESS_TTL_SECONDS")
    jwt_refresh_ttl_seconds: int = Field(default=1_209_600, alias="JWT_REFRESH_TTL_SECONDS")

    aws_region: str = Field(default="ap-northeast-2", alias="AWS_REGION")
    aws_endpoint_url: str | None = Field(default=None, alias="AWS_ENDPOINT_URL")
    sqs_reservation_queue_url: str = Field(..., alias="SQS_RESERVATION_QUEUE_URL")

    seat_hold_ttl_seconds: int = Field(default=2_592_000, alias="SEAT_HOLD_TTL_SECONDS")

    payment_cache_ttl_seconds: int = Field(default=3600, alias="PAYMENT_CACHE_TTL_SECONDS")
    # 예매는 취소로 변경 가능 → staleness 제한 위해 결제 캐시보다 짧게
    reservation_cache_ttl_seconds: int = Field(
        default=300,
        alias="RESERVATION_CACHE_TTL_SECONDS",
    )

    # 봇/매크로 억제용 ALTCHA PoW 캡차 — 기본 off(키 미설정 시 영향 없음)
    captcha_enabled: bool = Field(default=False, alias="CAPTCHA_ENABLED")
    captcha_hmac_secret: str = Field(default="", alias="CAPTCHA_HMAC_SECRET")
    captcha_complexity: int = Field(default=100_000, alias="CAPTCHA_COMPLEXITY")

    # 서비스 간 gRPC — 서버 listen 포트 + 클라이언트 타깃
    # 멀티 pod 는 dns:///<headless>:포트 형식으로 round_robin 분산
    grpc_port: int = Field(default=50051, alias="GRPC_PORT")
    event_grpc_target: str = Field(default="localhost:50051", alias="EVENT_GRPC_TARGET")
    reservation_grpc_target: str = Field(
        default="localhost:50051", alias="RESERVATION_GRPC_TARGET",
    )


settings = Settings()
