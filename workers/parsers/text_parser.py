from workers.parsers.base import ParsedDocument


def parse_text(content: bytes, *, file_type: str | None = None) -> ParsedDocument:
    """Parse UTF-8 text-like document bytes."""

    text = content.decode("utf-8", errors="replace")
    return ParsedDocument(text=text, metadata={"file_type": file_type or "txt"})
