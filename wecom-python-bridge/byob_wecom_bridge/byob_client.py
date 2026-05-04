from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from byob_wecom_bridge.settings import Settings


@dataclass(frozen=True)
class ByobAnswer:
    answer: str
    model: str | None
    source_count: int
    warnings: list[str]


class ByobClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token = settings.byob_api_token
        self._token_expires_at = float("inf") if self._token else 0.0
        self._timeout = settings.byob_bridge_timeout_ms / 1000
        self._client = httpx.AsyncClient(timeout=self._timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ask(self, question: str) -> ByobAnswer:
        token = await self._bearer_token()
        response = await self._client.post(
            f"{self._settings.byob_api_base_url}/api/v1/agent/ask",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "question": question[:4000],
                "top_k": self._settings.byob_agent_top_k,
                "use_llm": self._settings.byob_agent_use_llm,
            },
        )
        response.raise_for_status()
        payload = response.json()
        answer = payload.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("BYOB returned an empty answer")
        warnings = payload.get("warnings", [])
        return ByobAnswer(
            answer=answer.strip(),
            model=payload.get("model") if isinstance(payload.get("model"), str) else None,
            source_count=len(payload.get("sources", [])),
            warnings=[str(item) for item in warnings] if isinstance(warnings, list) else [],
        )

    async def _bearer_token(self) -> str:
        if self._token and self._token_expires_at > time.time() + 30:
            return self._token

        if not self._settings.byob_api_email or not self._settings.byob_api_password:
            raise RuntimeError("BYOB login credentials are not configured")

        response = await self._client.post(
            f"{self._settings.byob_api_base_url}/api/v1/auth/login",
            json={
                "email": self._settings.byob_api_email,
                "password": self._settings.byob_api_password,
            },
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("BYOB login did not return access_token")
        expires_in = payload.get("expires_in", 3600)
        try:
            expires_in_seconds = int(expires_in)
        except (TypeError, ValueError):
            expires_in_seconds = 3600
        self._token = token
        self._token_expires_at = time.time() + max(expires_in_seconds - 60, 60)
        return token
