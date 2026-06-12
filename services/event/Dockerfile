FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

# 의존성 메타데이터 먼저 — 소스 변경이 third-party 설치 레이어를 무효화하지 않도록
COPY pyproject.toml ./
COPY libs/common/pyproject.toml ./libs/common/
COPY libs/config/pyproject.toml ./libs/config/
COPY services/event/pyproject.toml ./services/event/
RUN uv sync --package cc-event --no-install-workspace

COPY libs ./libs
COPY services/event ./services/event
RUN uv sync --package cc-event

EXPOSE 8000

CMD ["uv", "run", "--package", "cc-event", "uvicorn", "event.main:app", "--host", "0.0.0.0", "--port", "8000"]
