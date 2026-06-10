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

    core_writer_url: str = Field(..., alias="CORE_WRITER_URL")
    core_reader_url: str = Field(..., alias="CORE_READER_URL")
    reservation_writer_url: str = Field(..., alias="RESERVATION_WRITER_URL")
    reservation_reader_url: str = Field(..., alias="RESERVATION_READER_URL")

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


settings = Settings()
