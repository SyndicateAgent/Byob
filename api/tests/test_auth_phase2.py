from uuid import uuid4

from fastapi import FastAPI
from pydantic import SecretStr
from starlette.requests import Request
from starlette.routing import Route

from api.app.config import Settings
from api.app.core.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    validate_api_key_format,
    verify_password,
)
from api.app.main import create_app
from api.app.middleware.auth import extract_api_key, path_requires_api_key


def test_password_hash_round_trip() -> None:
    """Password hashing verifies matching input and rejects different input."""

    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_jwt_round_trip_contains_tenant_context() -> None:
    """Management JWTs preserve user and tenant identity claims."""

    settings = Settings(
        app_env="test",
        jwt_secret_key=SecretStr("test-secret-with-32-bytes-minimum"),
    )
    user_id = uuid4()
    tenant_id = uuid4()

    token = create_access_token(
        settings,
        user_id=user_id,
        tenant_id=tenant_id,
        role="admin",
        email="admin@example.com",
    )
    payload = decode_access_token(settings, token)

    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == "admin"


def test_api_key_format_and_hashing() -> None:
    """Generated API keys follow the public format and are hashable."""

    api_key = generate_api_key()

    assert api_key.startswith("kb_live_")
    assert validate_api_key_format(api_key)
    assert len(hash_api_key(api_key)) == 64


def test_api_key_middleware_helpers() -> None:
    """API key middleware only protects external API paths and extracts supported headers."""

    assert path_requires_api_key("/api/v1/retrieval/search", ("/api/v1/retrieval",))
    assert not path_requires_api_key("/api/v1/auth/login", ("/api/v1/retrieval",))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/retrieval/search",
        "headers": [(b"x-api-key", b"kb_live_12345678901234567890123456789012")],
    }
    request = Request(scope)

    assert extract_api_key(request) == "kb_live_12345678901234567890123456789012"


def test_phase_two_routes_are_mounted() -> None:
    """Phase 2 management routes are registered under the versioned API prefix."""

    app: FastAPI = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if isinstance(route, Route)}

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/api-keys" in paths
    assert "/api/v1/usage" in paths
