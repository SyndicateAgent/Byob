from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any


def frame_get(frame: Any, *path: str) -> Any:
    current = frame
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
        if current is None:
            return None
    return current


def extract_chat_id(frame: Any) -> str | None:
    value = (
        frame_get(frame, "chat_id")
        or frame_get(frame, "chatId")
        or frame_get(frame, "header", "chat_id")
        or frame_get(frame, "header", "chatId")
        or frame_get(frame, "body", "chat_id")
        or frame_get(frame, "body", "chatId")
    )
    return str(value) if value else None


def extract_text(frame: Any) -> str:
    candidates = (
        frame_get(frame, "text"),
        frame_get(frame, "content"),
        frame_get(frame, "body", "text", "content"),
        frame_get(frame, "body", "content"),
        frame_get(frame, "message", "text", "content"),
        frame_get(frame, "message", "content"),
    )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def bind_event(client: Any, event: str, handler: Callable[..., Awaitable[None]]) -> None:
    if hasattr(client, "on"):
        client.on(event, handler)
        return
    if hasattr(client, "add_event_listener"):
        client.add_event_listener(event, handler)
        return
    raise RuntimeError("WeCom SDK client does not expose on() or add_event_listener()")


async def connect_client(client: Any) -> None:
    if hasattr(client, "connect"):
        await maybe_await(client.connect())
        return
    if hasattr(client, "connect_async"):
        await maybe_await(client.connect_async())
        return
    raise RuntimeError("WeCom SDK client does not expose connect()")


async def reply_text(
    client: Any,
    frame: Any,
    text: str,
    *,
    stream_id: str = "byob-python-bridge",
    finish: bool = True,
) -> None:
    if hasattr(client, "reply_stream"):
        await maybe_await(client.reply_stream(frame, stream_id, text, finish))
        return

    chat_id = extract_chat_id(frame)
    if not chat_id:
        raise RuntimeError("Cannot reply because chat_id was not found in WeCom frame")

    if hasattr(client, "send_message"):
        await maybe_await(
            client.send_message(
                chat_id,
                {
                    "msgtype": "markdown",
                    "markdown": {"content": text},
                },
            )
        )
        return

    if hasattr(client, "sendMessage"):
        await maybe_await(
            client.sendMessage(
                chat_id,
                {
                    "msgtype": "markdown",
                    "markdown": {"content": text},
                },
            )
        )
        return

    raise RuntimeError("WeCom SDK client does not expose reply_stream() or send_message()")
