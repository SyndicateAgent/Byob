FROM ghcr.io/astral-sh/uv:python3.12-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface

COPY pyproject.toml uv.lock alembic.ini ./
RUN uv sync --frozen --no-dev

COPY api ./api
COPY workers ./workers

CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
