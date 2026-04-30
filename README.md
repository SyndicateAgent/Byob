# BYOB

BYOB is an enterprise knowledge base BaaS for RAG infrastructure. This service exposes standardized APIs for external Agent frameworks and does not implement Agent orchestration, conversation state, or prompt templates.

## Local Development

```powershell
Copy-Item .env.example .env
docker compose up -d
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn api.app.main:app --reload
```

Docker Compose also starts Infinity-backed embedding and rerank services. The first startup downloads
`BAAI/bge-m3` and `BAAI/bge-reranker-base` into Docker volumes, so it can take several minutes.
Wait until `docker compose ps` shows both services as healthy before reprocessing documents.

Create the first management admin after migrations. If this reports missing tables, run `uv run alembic upgrade head` against the same `DATABASE_URL` first:

```powershell
$env:BYOB_ADMIN_EMAIL = "admin@example.com"
$env:BYOB_ADMIN_PASSWORD = "replace-with-a-strong-password"
uv run python -m api.scripts.seed_admin
```

If `BYOB_ADMIN_PASSWORD` is omitted, the script generates a strong password and prints it once. Existing users are not overwritten unless `BYOB_ADMIN_RESET_PASSWORD=true` is set.

Run the ingestion worker in a separate terminal when processing documents:

```powershell
uv run celery -A workers.celery_app.celery_app worker -Q ingestion --loglevel=INFO
```

On Windows the worker defaults to Celery's `solo` pool because the process pool can fail with
`billiard` handle errors.

Run the management console in a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

The console uses `NEXT_PUBLIC_API_BASE_URL` and defaults to `http://localhost:8000`.
The API allows browser requests from `CORS_ALLOWED_ORIGINS`, which defaults to local Next.js development origins.

Health and metrics endpoints:

- `GET /healthz`
- `GET /metrics`

Phase 3 management endpoints:

- `POST /api/v1/knowledge-bases`
- `POST /api/v1/knowledge-bases/{kb_id}/documents`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/text`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/url`
- `GET /api/v1/documents/{id}/chunks`

Retrieval endpoint:

- `POST /api/v1/retrieval/search`
- `POST /api/v1/retrieval/search/advanced`
- `POST /api/v1/retrieval/multi-search`
- `POST /api/v1/retrieval/rerank`
- `POST /api/v1/retrieval/embed`
- `POST /api/v1/retrieval/{request_id}/feedback`

Infrastructure services started by Docker Compose:

- PostgreSQL 16 on `localhost:5432`
- Redis 7 on `localhost:6379`
- Qdrant on `localhost:6333` and `localhost:6334`
- MinIO on `localhost:9000`, console on `localhost:9001`
- Infinity embedding on `localhost:7997`
- Infinity rerank on `localhost:7998`

Quality checks:

```powershell
uv run ruff check .
uv run mypy api
uv run pytest
cd frontend
npm run typecheck
npm run build
```
