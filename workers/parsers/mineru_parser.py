import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from workers.parsers.base import ParsedAsset, ParsedChunk, ParsedDocument

MINERU_DOCUMENT_FILE_TYPES = {"docx", "pdf", "ppt", "pptx", "xlsx"}
MINERU_IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class MineruParserConfig:
    """Settings required by the MinerU CLI."""

    command: str = "mineru"
    backend: str = "pipeline"
    parse_method: str = "auto"
    lang: str = "ch"
    timeout_seconds: int = 900
    api_url: str | None = None
    formula_enable: bool = True
    table_enable: bool = True


def parse_mineru_document(
    content: bytes,
    *,
    file_type: str,
    config: MineruParserConfig | None = None,
    source_name: str | None = None,
) -> ParsedDocument:
    """Parse a MinerU-supported file into text, typed chunks, and extracted assets."""

    normalized_type = file_type.lower().lstrip(".")
    if normalized_type not in MINERU_DOCUMENT_FILE_TYPES:
        raise ValueError(f"MinerU does not support document type: {normalized_type}")

    parser_config = config or MineruParserConfig()
    mineru_command = resolve_mineru_command(parser_config.command)
    with tempfile.TemporaryDirectory(prefix="byob_mineru_") as temp_dir:
        work_dir = Path(temp_dir)
        input_path = work_dir / f"{safe_input_stem(source_name)}.{normalized_type}"
        output_dir = work_dir / "output"
        input_path.write_bytes(content)
        run_mineru(mineru_command, input_path, output_dir, parser_config)
        parsed = read_mineru_output(output_dir, input_path.stem)
        return ParsedDocument(
            text=parsed.text,
            metadata={
                **parsed.metadata,
                "parser": "mineru",
                "mineru_backend": parser_config.backend,
                "mineru_parse_method": parser_config.parse_method,
                "mineru_lang": parser_config.lang,
                "mineru_file_type": normalized_type,
            },
            assets=parsed.assets,
            chunks=parsed.chunks,
        )


def resolve_mineru_command(command: str) -> str:
    """Resolve a MinerU command name or explicit executable path."""

    resolved = shutil.which(command)
    if resolved is not None:
        return resolved
    candidate = Path(command)
    if candidate.exists():
        return str(candidate)
    raise RuntimeError(
        f"MinerU command not found: {command}. Install MinerU or set MINERU_COMMAND."
    )


def run_mineru(
    mineru_command: str,
    input_path: Path,
    output_dir: Path,
    config: MineruParserConfig,
) -> None:
    """Run MinerU CLI for one input file."""

    command = [
        mineru_command,
        "-p",
        str(input_path),
        "-o",
        str(output_dir),
        "-b",
        config.backend,
        "-m",
        config.parse_method,
        "-l",
        config.lang,
        "-f",
        str(config.formula_enable).lower(),
        "-t",
        str(config.table_enable).lower(),
    ]
    if config.api_url:
        command.extend(["--api-url", config.api_url])

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=config.timeout_seconds,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:1000]
        raise RuntimeError(f"MinerU failed with exit code {result.returncode}: {detail}")


def read_mineru_output(output_dir: Path, document_stem: str) -> ParsedDocument:
    """Read MinerU content_list first, then markdown as a fallback preview."""

    content_list = choose_output_file(
        output_dir,
        [
            f"{document_stem}_content_list_v2.json",
            f"{document_stem}_content_list.json",
            "*_content_list_v2.json",
            "*_content_list.json",
        ],
    )
    if content_list is not None:
        payload = json.loads(content_list.read_text(encoding="utf-8"))
        text, metadata, chunks = content_list_to_chunks(payload)
        if text.strip():
            return ParsedDocument(
                text=text,
                metadata={**metadata, "mineru_output": "content_list"},
                assets=collect_image_assets(output_dir, [content_list.parent]),
                chunks=chunks,
            )

    markdown = choose_output_file(output_dir, [f"{document_stem}.md", "*.md"])
    if markdown is None:
        raise RuntimeError("MinerU did not produce markdown or content list output")
    return ParsedDocument(
        text=markdown.read_text(encoding="utf-8"),
        metadata={"mineru_output": "markdown"},
        assets=collect_image_assets(output_dir, [markdown.parent]),
    )


def choose_output_file(output_dir: Path, patterns: list[str]) -> Path | None:
    """Pick the largest matching MinerU output for broad fallback patterns."""

    for pattern in patterns:
        matches = [path for path in output_dir.rglob(pattern) if path.is_file()]
        if matches:
            return max(matches, key=lambda path: path.stat().st_size)
    return None


def content_list_to_chunks(payload: object) -> tuple[str, dict[str, object], list[ParsedChunk]]:
    """Convert MinerU content_list JSON into typed chunks and summary metadata."""

    if not isinstance(payload, list):
        raise RuntimeError("MinerU content list output is not a list")

    chunks: list[ParsedChunk] = []
    block_counts: Counter[str] = Counter()
    page_nums: set[int] = set()
    title_path: list[str] = []
    for raw_block in payload:
        if not isinstance(raw_block, dict):
            continue
        block_type = normalized_block_type(raw_block)
        block_counts[block_type] += 1
        page_num = page_number(raw_block)
        if page_num is not None:
            page_nums.add(page_num)
        heading_level = block_heading_level(raw_block, block_type)
        content = block_content(raw_block, block_type)
        if not content:
            continue
        if heading_level > 0:
            title_path = update_title_path(title_path, content, heading_level)
        chunks.append(
            ParsedChunk(
                content=content,
                chunk_type=chunk_type(block_type),
                page_num=page_num,
                bbox=block_bbox(raw_block),
                metadata=block_metadata(raw_block, block_type, heading_level, title_path),
            )
        )

    return "\n\n".join(chunk.content for chunk in chunks), {
        "page_count": len(page_nums),
        "mineru_content_blocks": sum(block_counts.values()),
        "mineru_block_types": dict(block_counts),
    }, chunks


def normalized_block_type(block: dict[str, object]) -> str:
    """Return a stable MinerU block type name."""

    return str(block.get("type") or "unknown").strip().lower() or "unknown"


def chunk_type(block_type: str) -> str:
    """Map MinerU block types to persisted chunk types."""

    if block_type in {"image", "chart"}:
        return "image"
    if block_type == "table":
        return "table"
    if block_type == "equation":
        return "equation"
    return "text"


def block_content(block: dict[str, object], block_type: str) -> str:
    """Build the searchable/renderable content for one MinerU block."""

    if block_type == "equation":
        latex = first_string(block.get("latex") or block.get("text") or block.get("content"))
        return f"$$\n{latex}\n$$" if latex else ""
    if block_type == "table":
        return joined_parts(
            block.get("caption") or block.get("table_caption"),
            block.get("table_body")
            or block.get("html")
            or block.get("text")
            or block.get("content"),
            block.get("footnote") or block.get("table_footnote"),
        )
    if block_type in {"image", "chart"}:
        caption = first_string(
            block.get("caption") or block.get("image_caption") or block.get("img_caption")
        )
        image_path = first_string(
            block.get("img_path")
            or block.get("image_path")
            or block.get("path")
            or block.get("src")
        )
        image_markdown = (
            f"![{escape_markdown_alt(caption or 'Image')}]({image_path})"
            if image_path
            else ""
        )
        return joined_parts(caption, image_markdown, block.get("content"), block.get("footnote"))
    if block_type == "list":
        return joined_parts(block.get("list_items"))
    if block_type == "code":
        return joined_parts(block.get("code_caption"), block.get("code_body"))
    return joined_parts(block.get("text") or block.get("content") or block.get("html"))


def block_metadata(
    block: dict[str, object],
    block_type: str,
    heading_level: int,
    title_path: list[str],
) -> dict[str, object]:
    """Build metadata for one typed chunk."""

    metadata: dict[str, object] = {"mineru_block_type": block_type}
    if title_path:
        metadata["title_path"] = list(title_path)
    if heading_level > 0:
        metadata["heading_level"] = heading_level
    if block_type == "table":
        add_first_string(
            metadata,
            "table_caption",
            block.get("caption") or block.get("table_caption"),
        )
    if block_type in {"image", "chart"}:
        add_first_string(
            metadata,
            "image_caption",
            block.get("caption") or block.get("image_caption") or block.get("img_caption"),
        )
        image_path = first_string(
            block.get("img_path")
            or block.get("image_path")
            or block.get("path")
            or block.get("src")
        )
        if image_path:
            metadata["image_path"] = normalize_asset_path(image_path)
    if block_type == "equation":
        add_first_string(
            metadata,
            "latex",
            block.get("latex") or block.get("text") or block.get("content"),
        )
    return metadata


def add_first_string(metadata: dict[str, object], key: str, value: object) -> None:
    """Add the first non-empty string from a MinerU scalar/list field."""

    text = first_string(value)
    if text:
        metadata[key] = text


def page_number(block: dict[str, object]) -> int | None:
    """Convert MinerU zero-based page_idx into a one-based page number."""

    page_idx = block.get("page_idx")
    return page_idx + 1 if isinstance(page_idx, int) else None


def block_bbox(block: dict[str, object]) -> dict[str, object] | None:
    """Normalize MinerU bbox-like fields for JSONB storage."""

    value = block.get("bbox") or block.get("position")
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list) and value:
        return {"points": value}
    return None


def block_heading_level(block: dict[str, object], block_type: str) -> int:
    """Return a heading level if MinerU marks a text block as a heading."""

    if block_type != "text":
        return 0
    level = block.get("level") or block.get("heading_level")
    if isinstance(level, int):
        return max(level, 0)
    if isinstance(level, str) and level.isdigit():
        return int(level)
    text = first_string(block.get("text") or block.get("content")) or ""
    match = re.match(r"^(#{1,6})\s+", text.strip())
    return len(match.group(1)) if match else 0


def update_title_path(title_path: list[str], heading_text: str, heading_level: int) -> list[str]:
    """Return the active title path after reading a heading block."""

    title = re.sub(r"^#{1,6}\s+", "", heading_text.strip()).splitlines()[0].strip()
    if not title:
        return title_path
    return [*title_path[: max(heading_level - 1, 0)], title]


def joined_parts(*values: object) -> str:
    """Flatten text-like MinerU fields and join non-empty parts."""

    parts: list[str] = []
    for value in values:
        parts.extend(flatten_strings(value))
    return "\n".join(part.strip() for part in parts if part.strip())


def flatten_strings(value: object) -> list[str]:
    """Flatten MinerU scalar/list fields into strings."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list):
        return [text for item in value for text in flatten_strings(item)]
    return []


def first_string(value: object) -> str | None:
    """Return the first non-empty string from a MinerU scalar/list field."""

    return next((text.strip() for text in flatten_strings(value) if text.strip()), None)


def collect_image_assets(output_dir: Path, relative_roots: list[Path]) -> list[ParsedAsset]:
    """Collect image files emitted by MinerU."""

    assets: list[ParsedAsset] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in MINERU_IMAGE_EXTENSIONS:
            continue
        aliases = source_path_aliases(path, output_dir, relative_roots)
        assets.append(
            ParsedAsset(
                source_path=aliases[0],
                content=path.read_bytes(),
                content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                metadata={"aliases": aliases},
            )
        )
    return assets


def source_path_aliases(path: Path, output_dir: Path, relative_roots: list[Path]) -> list[str]:
    """Return all relative paths MinerU may reference for one asset."""

    aliases: list[str] = []
    for root in [*relative_roots, output_dir]:
        try:
            alias = normalize_asset_path(path.relative_to(root))
        except ValueError:
            continue
        aliases.extend([alias, f"./{alias}"])
    return list(dict.fromkeys(aliases))


def safe_input_stem(source_name: str | None) -> str:
    """Return a stable, filesystem-safe input stem for MinerU."""

    stem = Path(source_name or "document").stem.strip()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return safe_stem or "document"


def normalize_asset_path(path: Path | str) -> str:
    """Normalize asset paths for Markdown/HTML replacement."""

    return str(path).replace("\\", "/")


def escape_markdown_alt(value: str) -> str:
    """Escape Markdown image alt text delimiters."""

    return value.replace("\\", "\\\\").replace("]", "\\]")