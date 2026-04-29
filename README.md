# Knowledge Base Platform

Enterprise knowledge base platform/BaaS for RAG infrastructure. This service exposes standardized APIs for external Agent frameworks and does not implement Agent orchestration, conversation state, or prompt templates.

## Local Development

```powershell
uv sync --extra dev
uv run uvicorn api.app.main:app --reload
```

Health and metrics endpoints:

- `GET /healthz`
- `GET /metrics`
