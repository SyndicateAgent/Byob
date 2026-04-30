# Phase 2 Summary

## Completed

- Added JWT-based management login for tenant-scoped users.
- Added API key creation, listing, and revocation endpoints under `/api/v1/auth`.
- Added API key generation, SHA256 hashing, one-time plaintext return, and format validation.
- Added API key authentication middleware for external API surfaces.
- Added tenant context propagation into request state, response headers, and structured logs.
- Added Redis sorted-set sliding-window rate limiting for authenticated API key requests.
- Added tenant usage listing endpoint under `/api/v1/usage`.
- Added Phase 2 security, middleware helper, and route registration tests.

## Notes And Pitfalls

- Existing Phase 1 tables already contained tenant, user, API key, and usage models, so Phase 2 did not add a migration.
- API key middleware currently protects future external prefixes such as `/api/v1/retrieval` and `/api/v1/chunks`; management endpoints use JWT.
- API key `last_used_at` is updated during authentication. This is correct but currently synchronous with the request path.
- A management user must exist in PostgreSQL before `/api/v1/auth/login` can issue JWTs; user provisioning remains outside this phase.

## Next Phase

- Add knowledge base CRUD endpoints with strict tenant filtering.
- Add document ingestion endpoints and background processing foundations.
- Reuse the authenticated tenant context for all knowledge base and document operations.
