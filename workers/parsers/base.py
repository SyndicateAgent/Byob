from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedChunk:
    """A structured chunk produced by a parser or chunking pass."""

    content: str
    chunk_type: str = "text"
    page_num: int | None = None
    bbox: dict[str, object] | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedAsset:
    """Binary asset extracted while parsing a source document."""

    source_path: str
    content: bytes
    content_type: str
    asset_type: str = "image"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Normalized parser output."""

    text: str
    metadata: dict[str, object] = field(default_factory=dict)
    assets: list[ParsedAsset] = field(default_factory=list)
    chunks: list[ParsedChunk] = field(default_factory=list)
