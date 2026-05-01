import json
import mimetypes
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from pypdf import PdfReader

from workers.parsers.base import ParsedAsset, ParsedDocument

IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


@dataclass(frozen=True)
class PdfParserConfig:
    """Runtime configuration for PDF parsing."""

    parser: Literal["mineru", "pypdf"] = "mineru"
    mineru_command: str = "mineru"
    mineru_backend: str = "pipeline"
    mineru_parse_method: str = "auto"
    mineru_lang: str = "ch"
    mineru_timeout_seconds: int = 900
    mineru_api_url: str | None = None
    mineru_formula_enable: bool = True
    mineru_table_enable: bool = True
    mineru_fallback_to_pypdf: bool = True


def parse_pdf(content: bytes, config: PdfParserConfig | None = None) -> ParsedDocument:
    """Extract text from a PDF document, preferring MinerU for layout-aware parsing."""

    parser_config = config or PdfParserConfig()
    if parser_config.parser == "pypdf":
        return parse_pdf_with_pypdf(content)

    try:
        return parse_pdf_with_mineru(content, parser_config)
    except Exception as exc:
        if not parser_config.mineru_fallback_to_pypdf:
            raise
        parsed = parse_pdf_with_pypdf(content)
        return ParsedDocument(
            text=parsed.text,
            metadata={
                **parsed.metadata,
                "mineru_fallback": True,
                "mineru_error": str(exc)[:1000],
            },
        )


def parse_pdf_with_mineru(content: bytes, config: PdfParserConfig) -> ParsedDocument:
    """Parse a PDF through the MinerU CLI and read its structured output."""

    mineru_command = shutil.which(config.mineru_command)
    if mineru_command is None:
        candidate = Path(config.mineru_command)
        if candidate.exists():
            mineru_command = str(candidate)
        else:
            raise RuntimeError(
                f"MinerU command not found: {config.mineru_command}. "
                "Install MinerU or set MINERU_COMMAND."
            )

    with tempfile.TemporaryDirectory(prefix="byob_mineru_") as temp_dir:
        work_dir = Path(temp_dir)
        input_path = work_dir / "document.pdf"
        output_dir = work_dir / "output"
        input_path.write_bytes(content)

        command = [
            mineru_command,
            "-p",
            str(input_path),
            "-o",
            str(output_dir),
            "-b",
            config.mineru_backend,
            "-m",
            config.mineru_parse_method,
            "-l",
            config.mineru_lang,
            "-f",
            str(config.mineru_formula_enable).lower(),
            "-t",
            str(config.mineru_table_enable).lower(),
        ]
        if config.mineru_api_url:
            command.extend(["--api-url", config.mineru_api_url])

        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.mineru_timeout_seconds,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"MinerU failed with exit code {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()[:1000]}"
            )

        text, metadata, assets = read_mineru_output(output_dir, input_path.stem)
        if not text.strip():
            raise RuntimeError("MinerU produced empty text output")
        return ParsedDocument(
            text=text,
            metadata={
                **metadata,
                "parser": "mineru",
                "mineru_backend": config.mineru_backend,
                "mineru_parse_method": config.mineru_parse_method,
                "mineru_lang": config.mineru_lang,
            },
            assets=assets,
        )


def parse_pdf_with_pypdf(content: bytes) -> ParsedDocument:
    """Extract text from a PDF document with pypdf as a lightweight fallback."""

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return ParsedDocument(
        text="\n\n".join(pages),
        metadata={"parser": "pypdf", "page_count": len(reader.pages)},
    )


def read_mineru_output(
    output_dir: Path,
    document_stem: str,
) -> tuple[str, dict[str, object], list[ParsedAsset]]:
    """Read the best available text representation from MinerU output files."""

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
        text, metadata = extract_text_from_content_list(payload)
        if text.strip():
            assets = collect_image_assets(output_dir, [content_list.parent])
            return text, {**metadata, "mineru_output": "content_list"}, assets

    markdown = choose_output_file(output_dir, [f"{document_stem}.md", "*.md"])
    if markdown is None:
        raise RuntimeError("MinerU did not produce markdown or content list output")
    assets = collect_image_assets(output_dir, [markdown.parent])
    return markdown.read_text(encoding="utf-8"), {"mineru_output": "markdown"}, assets


def choose_output_file(output_dir: Path, patterns: list[str]) -> Path | None:
    """Choose a MinerU output file, preferring larger files for broad fallback patterns."""

    for pattern in patterns:
        matches = [path for path in output_dir.rglob(pattern) if path.is_file()]
        if matches:
            return max(matches, key=lambda path: path.stat().st_size)
    return None


def extract_text_from_content_list(payload: object) -> tuple[str, dict[str, object]]:
    """Convert MinerU content-list blocks into RAG-friendly plain text."""

    if not isinstance(payload, list):
        raise RuntimeError("MinerU content list output is not a list")

    blocks: list[str] = []
    block_counts: Counter[str] = Counter()
    page_indices: set[int] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        block_type = str(item.get("type") or "unknown")
        block_counts[block_type] += 1
        page_idx = item.get("page_idx")
        if isinstance(page_idx, int):
            page_indices.add(page_idx)
        block_text = extract_text_from_content_block(item)
        if block_text:
            blocks.append(block_text)

    return "\n\n".join(blocks), {
        "page_count": len(page_indices),
        "mineru_content_blocks": sum(block_counts.values()),
        "mineru_block_types": dict(block_counts),
    }


def extract_text_from_content_block(item: dict[str, object]) -> str:
    """Extract useful searchable text from one MinerU content-list block."""

    block_type = str(item.get("type") or "")
    parts: list[str] = []
    if block_type in {"text", "equation"}:
        parts.extend(flatten_strings(item.get("text")))
    elif block_type == "table":
        parts.extend(flatten_strings(item.get("caption") or item.get("table_caption")))
        parts.extend(flatten_strings(item.get("html") or item.get("text") or item.get("content")))
        parts.extend(flatten_strings(item.get("footnote") or item.get("table_footnote")))
    elif block_type in {"image", "chart"}:
        asset_path = first_string(
            item.get("img_path")
            or item.get("image_path")
            or item.get("path")
            or item.get("src")
        )
        parts.extend(flatten_strings(item.get("caption") or item.get("image_caption")))
        if asset_path:
            alt_text = first_string(item.get("caption") or item.get("image_caption")) or "Image"
            parts.append(f"![{escape_markdown_alt(alt_text)}]({asset_path})")
        parts.extend(flatten_strings(item.get("content")))
        parts.extend(flatten_strings(item.get("footnote") or item.get("image_footnote")))
    elif block_type == "list":
        parts.extend(flatten_strings(item.get("list_items")))
    elif block_type == "code":
        parts.extend(flatten_strings(item.get("code_caption")))
        parts.extend(flatten_strings(item.get("code_body")))
    else:
        parts.extend(flatten_strings(item.get("text") or item.get("content") or item.get("html")))
    return "\n".join(part.strip() for part in parts if part.strip())


def flatten_strings(value: object) -> list[str]:
    """Flatten MinerU scalar/list fields into strings."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(flatten_strings(item))
        return values
    return []


def first_string(value: object) -> str | None:
    """Return the first non-empty string flattened from a MinerU field."""

    for item in flatten_strings(value):
        stripped = item.strip()
        if stripped:
            return stripped
    return None


def escape_markdown_alt(value: str) -> str:
    """Escape Markdown image alt text delimiters."""

    return value.replace("\\", "\\\\").replace("]", "\\]")


def collect_image_assets(output_dir: Path, relative_roots: list[Path]) -> list[ParsedAsset]:
    """Collect image files emitted by MinerU and record useful source path aliases."""

    assets: list[ParsedAsset] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        aliases = source_path_aliases(path, output_dir, relative_roots)
        source_path = aliases[0]
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        assets.append(
            ParsedAsset(
                source_path=source_path,
                content=path.read_bytes(),
                content_type=content_type,
                metadata={"aliases": aliases},
            )
        )
    return assets


def source_path_aliases(path: Path, output_dir: Path, relative_roots: list[Path]) -> list[str]:
    """Return normalized relative aliases that may appear in MinerU Markdown/JSON."""

    aliases: list[str] = []
    roots = [*relative_roots, output_dir]
    for root in roots:
        try:
            alias = normalize_asset_path(path.relative_to(root))
        except ValueError:
            continue
        aliases.append(alias)
        aliases.append(f"./{alias}")
    return list(dict.fromkeys(aliases))


def normalize_asset_path(path: Path | str) -> str:
    """Normalize asset paths for cross-platform Markdown replacement."""

    return str(path).replace("\\", "/")
