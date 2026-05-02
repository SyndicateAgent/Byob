from dataclasses import dataclass, field
from re import Match, compile, search, sub

MARKDOWN_IMAGE_PATTERN = compile(r"!\s*\[\s*(?P<alt>[^\]]*?)\s*\]\s*\(\s*(?P<target>[^)]+?)\s*\)")
STRUCTURED_TOKEN_PATTERN = compile(
    r"^(?:!?\[[^\]]*]\([^)]+\)|https?://\S+|/api/\S+|\.?/?images/\S+)"
)


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
    if words and is_structured_token(words[0]):
        return words
    return [character for character in paragraph if not character.isspace()]


def contains_cjk(text: str) -> bool:
    """Return whether text contains Chinese/Japanese/Korean characters."""

    return search(r"[\u3400-\u9fff]", text) is not None


def join_tokens(tokens: list[str]) -> str:
    """Reconstruct text without adding spaces to character-tokenized CJK chunks."""

    if all(len(token) == 1 for token in tokens):
        return normalize_markdown_image_references("".join(tokens))
    return normalize_markdown_image_references(" ".join(tokens))


def is_structured_token(token: str) -> bool:
    """Return whether a single whitespace-free token should stay intact."""

    return STRUCTURED_TOKEN_PATTERN.search(token) is not None


def normalize_markdown_image_references(text: str) -> str:
    """Collapse accidental spaces inside Markdown image references."""

    def replace_reference(match: Match[str]) -> str:
        alt = match.group("alt").strip()
        target = normalize_asset_target(match.group("target"))
        return f"![{alt}]({target})"

    return MARKDOWN_IMAGE_PATTERN.sub(replace_reference, text)


def normalize_asset_target(target: str) -> str:
    """Remove character-spacing from known generated asset URLs and image paths."""

    stripped = target.strip()
    compact = sub(r"\s+", "", stripped)
    if compact.startswith(("/api/", "http://", "https://", "images/", "./images/")):
        return compact
    return stripped
