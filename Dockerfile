FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
COPY libs ./libs
COPY app ./app

RUN uv sync

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]