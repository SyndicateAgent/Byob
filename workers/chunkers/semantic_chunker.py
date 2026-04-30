from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedChunk:
    """A chunk produced from parsed document text."""

    content: str
    chunk_type: str = "text"
    metadata: dict[str, object] = field(default_factory=dict)


def chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[ParsedChunk]:
    """Split text by paragraph boundaries with token-like size limits."""

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    chunks: list[ParsedChunk] = []
    current_words: list[str] = []

    for paragraph in paragraphs:
        words = paragraph.split()
        if len(current_words) + len(words) <= chunk_size:
            current_words.extend(words)
            continue

        if current_words:
            chunks.append(ParsedChunk(content=" ".join(current_words)))
        overlap = current_words[-chunk_overlap:] if chunk_overlap > 0 else []
        current_words = [*overlap, *words]

        while len(current_words) > chunk_size:
            chunks.append(ParsedChunk(content=" ".join(current_words[:chunk_size])))
            overlap = (
                current_words[chunk_size - chunk_overlap : chunk_size]
                if chunk_overlap > 0
                else []
            )
            current_words = [*overlap, *current_words[chunk_size:]]

    if current_words:
        chunks.append(ParsedChunk(content=" ".join(current_words)))

    return chunks
