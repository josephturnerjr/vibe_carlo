FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN uv sync --frozen --no-dev


RUN useradd --system --uid 10000 --no-create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

ENV VIBE_CARLO_DB=/data/vibe_carlo.db
ENV VIBE_CARLO_SECURE_COOKIES=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["curl", "-f", "http://localhost:8000/health"]

CMD ["uv", "run", "uvicorn", "vibe_carlo.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
