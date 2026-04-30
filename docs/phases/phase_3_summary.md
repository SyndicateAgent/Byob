# Phase 3 Summary

## Completed

- Added tenant-scoped knowledge base CRUD, detail, delete, and stats endpoints.
- Added document ingestion endpoints for file upload, direct text, and URL sources.
- Added document listing, detail, chunk listing, delete, and reprocess endpoints.
- Added PDF, DOCX, Markdown, TXT, and simple HTML/URL parser support.
- Added paragraph-aware chunking with overlap support.
- Added an Infinity/OpenAI-compatible embedding client for BGE-M3 deployments.
- Added Celery ingestion tasks with retry/backoff for parse -> chunk -> embed -> persist -> Qdrant upsert.
- Added Qdrant hybrid collection creation with dense and sparse vectors.
- Added document status transitions for pending, processing, completed, and failed states.
- Added focused Phase 3 tests for route registration, parsing/chunking, and Qdrant payload safety.

## Notes And Pitfalls

- MinIO stores uploaded source files; PostgreSQL remains the source of truth for chunk content.
- Qdrant payloads contain only identifiers and filter fields, not chunk source text.
- The sparse keyword vector is deterministic and local; retrieval scoring refinements belong in Phase 4.
- A running Celery worker and embedding endpoint are required for real asynchronous document processing.
- URL ingestion uses a minimal HTML-to-text fallback and should be hardened before production crawling.

## Next Phase

- Implement retrieval APIs over Qdrant dense and sparse vectors.
- Add RRF or weighted fusion for hybrid results.
- Add rerank service integration and full retrieval logging.
