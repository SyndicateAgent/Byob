from dataclasses import dataclass, field


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
