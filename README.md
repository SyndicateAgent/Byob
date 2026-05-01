# BYOB

BYOB is a self-hosted vector database management system for AI Agent retrieval. It provides knowledge base management, document ingestion, chunk storage, Qdrant-backed hybrid search, embedding, rerank, and a local management console.

BYOB does not implement Agent orchestration, conversation state, prompt templates, tenant management, API key management, billing, or usage analytics.

## Local Development

```powershell
Copy-Item .env.example .env
docker compose up -d
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn api.app.main:app --reload
```

Docker Compose also starts Infinity-backed embedding and rerank services. The first startup downloads `BAAI/bge-m3` and `BAAI/bge-reranker-base` into Docker volumes, so it can take several minutes. Wait until `docker compose ps` shows both services as healthy before reprocessing documents.

PDF ingestion prefers MinerU for layout-aware parsing, table/formula extraction, and OCR-friendly output. Install MinerU in the Python environment used by the worker before processing PDFs:

```powershell
uv pip install "mineru[core]"
```

The parser is controlled by `PDF_PARSER`, `MINERU_BACKEND`, `MINERU_PARSE_METHOD`, `MINERU_LANG`, and related settings in `.env`. If MinerU is unavailable and `MINERU_FALLBACK_TO_PYPDF=true`, BYOB falls back to `pypdf` so local development can continue.

Create the first local management admin after migrations. If this reports missing tables, run `uv run alembic upgrade head` against the same `DATABASE_URL` first:

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

On Windows the worker defaults to Celery's `solo` pool because the process pool can fail with `billiard` handle errors.

File import supports selecting multiple files at once. BYOB skips a file automatically when another document in the same knowledge base already has the same document name or SHA-256 file hash.

Run the management console in a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

The console uses `NEXT_PUBLIC_API_BASE_URL` and defaults to `http://localhost:8000`. The API allows browser requests from `CORS_ALLOWED_ORIGINS`, which defaults to local Next.js development origins.

## API Surface

Management endpoints use JWT login for local console users:

- `POST /api/v1/auth/login`
- `GET /api/v1/users`
- `POST /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`

Knowledge base and document endpoints:

- `POST /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases`
- `GET /api/v1/knowledge-bases/{kb_id}`
- `PATCH /api/v1/knowledge-bases/{kb_id}`
- `DELETE /api/v1/knowledge-bases/{kb_id}`
- `GET /api/v1/knowledge-bases/{kb_id}/stats`
- `POST /api/v1/knowledge-bases/{kb_id}/documents`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/batch`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/text`
- `POST /api/v1/knowledge-bases/{kb_id}/documents/url`
- `GET /api/v1/knowledge-bases/{kb_id}/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/chunks`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/reprocess`

Retrieval endpoints are direct local APIs intended for AI Agents running in the same trusted deployment environment:

- `POST /api/v1/retrieval/search`
- `POST /api/v1/retrieval/search/advanced`
- `POST /api/v1/retrieval/multi-search`
- `POST /api/v1/retrieval/rerank`
- `POST /api/v1/retrieval/embed`
- `POST /api/v1/retrieval/{request_id}/feedback`

Health and metrics endpoints:

- `GET /healthz`
- `GET /metrics`

## Infrastructure Services

Docker Compose starts:

- PostgreSQL 16 on `localhost:5432`
- Redis 7 on `localhost:6379`
- Qdrant on `localhost:6333` and `localhost:6334`
- MinIO on `localhost:9000`, console on `localhost:9001`
- Infinity embedding on `localhost:7997`
- Infinity rerank on `localhost:7998`

## Quality Checks

```powershell
uv run ruff check .
uv run pytest
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```
