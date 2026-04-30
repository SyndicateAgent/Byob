# Knowledge Base Platform

Enterprise knowledge base platform/BaaS for RAG infrastructure. This service exposes standardized APIs for external Agent frameworks and does not implement Agent orchestration, conversation state, or prompt templates.

## Local Development

```powershell
Copy-Item .env.example .env
docker compose up -d
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn api.app.main:app --reload
```

Run the ingestion worker in a separate terminal when processing documents:

```powershell
uv run celery -A workers.celery_app.celery_app worker -Q ingestion --loglevel=INFO
```

Health and metrics endpoints:

- `GET /healthz`
- `GET /metrics`

Phase 3 management endpoints:

- `POST /api/v1/knowledge-bases`
- `POST /api/v1/knowledge-bases/{kb_id}/documents`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/text`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/url`
- `GET /api/v1/documents/{id}/chunks`

Infrastructure services started by Docker Compose:

- PostgreSQL 16 on `localhost:5432`
- Redis 7 on `localhost:6379`
- Qdrant on `localhost:6333` and `localhost:6334`
- MinIO on `localhost:9000`, console on `localhost:9001`

Quality checks:

```powershell
uv run ruff check .
uv run mypy api
uv run pytest
```
