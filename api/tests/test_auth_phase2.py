from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.routing import Route

from api.app.config import Settings
from api.app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from api.app.main import create_app


def test_password_hash_round_trip() -> None:
    """Password hashing verifies matching input and rejects different input."""

    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_jwt_round_trip_contains_user_context() -> None:
    """Management JWTs preserve local user identity claims."""

    settings = Settings(
        app_env="test",
        jwt_secret_key=SecretStr("test-secret-with-32-bytes-minimum"),
    )
    user_id = uuid4()

    token = create_access_token(
        settings,
        user_id=user_id,
        role="admin",
        email="admin@example.com",
    )
    payload = decode_access_token(settings, token)

    assert payload["sub"] == str(user_id)
    assert payload["role"] == "admin"


def test_phase_two_routes_are_mounted() -> None:
    """Phase 2 management routes are registered under the versioned API prefix."""

    app: FastAPI = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if isinstance(route, Route)}

    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/api-keys" not in paths
    assert "/api/v1/usage" not in paths


@pytest.mark.asyncio
async def test_cors_preflight_allows_local_console_origin() -> None:
    """Browser preflight requests from the local console should not hit route 405s."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
