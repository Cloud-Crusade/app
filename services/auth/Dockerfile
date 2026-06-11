FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

# 의존성 메타데이터 먼저 — 소스 변경이 third-party 설치 레이어를 무효화하지 않도록
COPY pyproject.toml ./
COPY libs/common/pyproject.toml ./libs/common/
COPY libs/config/pyproject.toml ./libs/config/
COPY services/auth/pyproject.toml ./services/auth/
RUN uv sync --package cc-auth --no-install-workspace

COPY libs ./libs
COPY services/auth ./services/auth
RUN uv sync --package cc-auth

EXPOSE 8000

CMD ["uv", "run", "--package", "cc-auth", "uvicorn", "auth.main:app", "--host", "0.0.0.0", "--port", "8000"]
