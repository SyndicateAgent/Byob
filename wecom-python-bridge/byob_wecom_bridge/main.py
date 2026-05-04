from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import uuid4

from byob_wecom_bridge.byob_client import ByobClient
from byob_wecom_bridge.settings import Settings, load_settings
from byob_wecom_bridge.wecom_adapter import bind_event, connect_client, extract_text, reply_text

LOGGER = logging.getLogger("byob-wecom-bridge")


def _build_wecom_client(settings: Settings) -> Any:
    try:
        from wecom_aibot_sdk import WSClient
    except ImportError as exc:
        raise RuntimeError(
            "wecom-aibot-sdk is not installed. Run `pip install -e .` in wecom-python-bridge."
        ) from exc

    try:
        return WSClient(bot_id=settings.wecom_bot_id, secret=settings.wecom_secret)
    except TypeError:
        return WSClient(settings.wecom_bot_id, settings.wecom_secret)


def clamp_answer(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 32].rstrip()}\n\n...[truncated by bridge]"


async def run_async() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = load_settings()
    byob = ByobClient(settings)
    client = _build_wecom_client(settings)

    async def on_authenticated(*_: Any) -> None:
        LOGGER.info("WeCom long connection authenticated")

    async def on_text(frame: Any) -> None:
        question = extract_text(frame)
        stream_id = f"byob-python-bridge-{uuid4().hex}"
        if not question:
            await reply_text(client, frame, "当前 Python bridge 只处理文本消息。")
            return

        LOGGER.info("Forwarding WeCom text to BYOB, chars=%s", len(question))
        if settings.send_thinking_message:
            await reply_text(
                client,
                frame,
                "正在检索 BYOB 知识库，请稍等...",
                stream_id=stream_id,
                finish=False,
            )

        try:
            result = await byob.ask(question)
            LOGGER.info(
                "BYOB answer ready, model=%s, sources=%s, warnings=%s",
                result.model,
                result.source_count,
                len(result.warnings),
            )
            await reply_text(
                client,
                frame,
                clamp_answer(result.answer, settings.byob_text_max_chars),
                stream_id=stream_id,
                finish=True,
            )
        except Exception:
            LOGGER.exception("BYOB bridge request failed")
            await reply_text(client, frame, "BYOB Python bridge 调用失败，请查看本机日志。")

    async def on_non_text(frame: Any) -> None:
        await reply_text(client, frame, "当前 Python bridge 只处理文本消息。")

    bind_event(client, "authenticated", on_authenticated)
    bind_event(client, "message.text", on_text)
    bind_event(client, "message.image", on_non_text)
    bind_event(client, "message.mixed", on_non_text)
    bind_event(client, "message.file", on_non_text)
    bind_event(client, "message.voice", on_non_text)
    bind_event(client, "message.video", on_non_text)

    try:
        LOGGER.info("Connecting to WeCom long-connection gateway")
        await connect_client(client)
        await asyncio.Event().wait()
    finally:
        await byob.aclose()


def run() -> None:
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
