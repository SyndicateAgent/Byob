import re
from collections.abc import Iterable

from workers.parsers.base import ParsedChunk

MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\s*\[\s*(?P<alt>[^\]]*?)\s*]\s*\(\s*(?P<target>[^)]+?)\s*\)"
)
LOCAL_ASSET_PREFIXES = ("/api/", "http://", "https://", "images/", "./images/")


def chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[ParsedChunk]:
    """Chunk plain text by paragraph, preserving CJK and Markdown asset references."""

    paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
    return merge_structured_chunks(
        [ParsedChunk(content=paragraph) for paragraph in paragraphs],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def merge_structured_chunks(
    chunks: list[ParsedChunk],
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[ParsedChunk]:
    """Merge adjacent text chunks while keeping table/image/equation chunks atomic."""

    options = ChunkOptions(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    output: list[ParsedChunk] = []
    pending = TextBuffer(options)
    for chunk in chunks:
        if not chunk.content.strip():
            continue
        if chunk.chunk_type != "text":
            output.extend(pending.flush())
            output.append(chunk)
            continue
        if is_heading(chunk):
            output.extend(pending.flush())
        output.extend(pending.add(chunk))
    output.extend(pending.flush())
    return output


class ChunkOptions:
    """Validated chunk size settings."""

    def __init__(self, *, chunk_size: int, chunk_overlap: int) -> None:
        self.chunk_size = max(chunk_size, 1)
        self.chunk_overlap = max(min(chunk_overlap, self.chunk_size - 1), 0)


class TextBuffer:
    """Accumulates text tokens until a configured chunk boundary is reached."""

    def __init__(self, options: ChunkOptions) -> None:
        self.options = options
        self.tokens: list[str] = []
        self.page_num: int | None = None
        self.bbox: dict[str, object] | None = None
        self.metadata: dict[str, object] = {}

    def add(self, chunk: ParsedChunk) -> list[ParsedChunk]:
        produced: list[ParsedChunk] = []
        tokens = tokenize(chunk.content)
        if not tokens:
            return produced
        if len(tokens) > self.options.chunk_size:
            produced.extend(self.flush())
            produced.extend(split_large_chunk(chunk, tokens, self.options))
            return produced
        if not self.tokens:
            self.start(chunk)
        if len(self.tokens) + len(tokens) > self.options.chunk_size:
            overlap = (
                self.tokens[-self.options.chunk_overlap :]
                if self.options.chunk_overlap
                else []
            )
            produced.extend(self.flush())
            self.start(chunk, initial_tokens=overlap)
        self.tokens.extend(tokens)
        return produced

    def flush(self) -> list[ParsedChunk]:
        if not self.tokens:
            return []
        chunk = ParsedChunk(
            content=join_tokens(self.tokens),
            page_num=self.page_num,
            bbox=self.bbox,
            metadata=self.metadata,
        )
        self.tokens = []
        self.page_num = None
        self.bbox = None
        self.metadata = {}
        return [chunk]

    def start(self, chunk: ParsedChunk, initial_tokens: list[str] | None = None) -> None:
        self.tokens = list(initial_tokens or [])
        self.page_num = chunk.page_num
        self.bbox = chunk.bbox
        self.metadata = dict(chunk.metadata)


def split_large_chunk(
    chunk: ParsedChunk,
    tokens: list[str],
    options: ChunkOptions,
) -> list[ParsedChunk]:
    """Split one oversized text block into bounded text chunks."""

    output: list[ParsedChunk] = []
    start = 0
    while start < len(tokens):
        end = min(start + options.chunk_size, len(tokens))
        output.append(
            ParsedChunk(
                content=join_tokens(tokens[start:end]),
                page_num=chunk.page_num,
                bbox=chunk.bbox,
                metadata=dict(chunk.metadata),
            )
        )
        if end == len(tokens):
            break
        start = end - options.chunk_overlap if options.chunk_overlap else end
    return output


def tokenize(text: str) -> list[str]:
    """Tokenize by words for spaced text and by characters for CJK-heavy text."""

    if contains_cjk(text):
        return [character for character in text if not character.isspace()]
    return text.split()


def join_tokens(tokens: Iterable[str]) -> str:
    """Join tokens while preserving CJK text and repairing spaced Markdown images."""

    token_list = list(tokens)
    if all(len(token) == 1 for token in token_list):
        return normalize_markdown_image_references("".join(token_list))
    return normalize_markdown_image_references(" ".join(token_list))


def normalize_markdown_image_references(text: str) -> str:
    """Collapse accidental spaces inside Markdown image references."""

    def replace_reference(match: re.Match[str]) -> str:
        target = normalize_asset_target(match.group("target"))
        return f"![{match.group('alt').strip()}]({target})"

    return MARKDOWN_IMAGE_PATTERN.sub(replace_reference, text)


def normalize_asset_target(target: str) -> str:
    """Compact local/remote image targets that tokenization may have spaced apart."""

    compact = re.sub(r"\s+", "", target.strip())
    return compact if compact.startswith(LOCAL_ASSET_PREFIXES) else target.strip()


def contains_cjk(text: str) -> bool:
    """Return whether text contains Chinese, Japanese, or Korean characters."""

    return re.search(r"[\u3400-\u9fff]", text) is not None


def is_heading(chunk: ParsedChunk) -> bool:
    """Return whether a text chunk starts a new heading section."""

    heading_level = chunk.metadata.get("heading_level")
    return isinstance(heading_level, int) and heading_level > 0