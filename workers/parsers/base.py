from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedDocument:
    """Normalized parser output."""

    text: str
    metadata: dict[str, object] = field(default_factory=dict)
