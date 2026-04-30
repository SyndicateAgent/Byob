from dataclasses import dataclass, field
from re import search


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
    current_tokens: list[str] = []

    for paragraph in paragraphs:
        tokens = tokenize_paragraph(paragraph)
        if len(current_tokens) + len(tokens) <= chunk_size:
            current_tokens.extend(tokens)
            continue

        if current_tokens:
            chunks.append(ParsedChunk(content=join_tokens(current_tokens)))
        overlap = current_tokens[-chunk_overlap:] if chunk_overlap > 0 else []
        current_tokens = [*overlap, *tokens]

        while len(current_tokens) > chunk_size:
            chunks.append(ParsedChunk(content=join_tokens(current_tokens[:chunk_size])))
            overlap = (
                current_tokens[chunk_size - chunk_overlap : chunk_size]
                if chunk_overlap > 0
                else []
            )
            current_tokens = [*overlap, *current_tokens[chunk_size:]]

    if current_tokens:
        chunks.append(ParsedChunk(content=join_tokens(current_tokens)))

    return chunks


def tokenize_paragraph(paragraph: str) -> list[str]:
    """Tokenize whitespace-delimited text, falling back to characters for CJK PDFs."""

    if contains_cjk(paragraph):
        return [character for character in paragraph if not character.isspace()]

    words = paragraph.split()
    if len(words) > 1:
        return words
    return [character for character in paragraph if not character.isspace()]


def contains_cjk(text: str) -> bool:
    """Return whether text contains Chinese/Japanese/Korean characters."""

    return search(r"[\u3400-\u9fff]", text) is not None


def join_tokens(tokens: list[str]) -> str:
    """Reconstruct text without adding spaces to character-tokenized CJK chunks."""

    if all(len(token) == 1 for token in tokens):
        return "".join(tokens)
    return " ".join(tokens)
