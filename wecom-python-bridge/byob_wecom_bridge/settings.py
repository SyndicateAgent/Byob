from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE lines without overwriting existing environment values."""

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def int_env(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(os.environ.get(name, str(default)))
    except ValueError:
        parsed = default
    if minimum is not None:
        parsed = max(parsed, minimum)
    if maximum is not None:
        parsed = min(parsed, maximum)
    return parsed


@dataclass(frozen=True)
class Settings:
    wecom_bot_id: str
    wecom_secret: str
    byob_api_base_url: str
    byob_api_email: str | None
    byob_api_password: str | None
    byob_api_token: str | None
    byob_agent_use_llm: bool
    byob_agent_top_k: int
    byob_bridge_timeout_ms: int
    byob_text_max_chars: int
    send_thinking_message: bool


def load_settings() -> Settings:
    bridge_root = Path(__file__).resolve().parents[1]
    load_env_file(bridge_root / "env.local")

    bot_id = os.environ.get("WECOM_BOT_ID", "").strip()
    secret = os.environ.get("WECOM_SECRET", "").strip()
    if not bot_id:
        raise RuntimeError("WECOM_BOT_ID is required")
    if not secret:
        raise RuntimeError("WECOM_SECRET is required")

    static_token = os.environ.get("BYOB_API_TOKEN", "").strip() or None
    email = os.environ.get("BYOB_API_EMAIL", "").strip() or None
    password = os.environ.get("BYOB_API_PASSWORD", "") or None
    if not static_token and not (email and password):
        raise RuntimeError("Set BYOB_API_TOKEN or BYOB_API_EMAIL/BYOB_API_PASSWORD")

    return Settings(
        wecom_bot_id=bot_id,
        wecom_secret=secret,
        byob_api_base_url=os.environ.get("BYOB_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        byob_api_email=email,
        byob_api_password=password,
        byob_api_token=static_token,
        byob_agent_use_llm=truthy(os.environ.get("BYOB_AGENT_USE_LLM"), default=True),
        byob_agent_top_k=int_env("BYOB_AGENT_TOP_K", 5, minimum=1, maximum=20),
        byob_bridge_timeout_ms=int_env("BYOB_BRIDGE_TIMEOUT_MS", 180000, minimum=1000),
        byob_text_max_chars=int_env("BYOB_TEXT_MAX_CHARS", 12000, minimum=500),
        send_thinking_message=truthy(os.environ.get("BYOB_SEND_THINKING_MESSAGE"), default=True),
    )
