import base64
import binascii
import mimetypes
import re
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

from workers.parsers.base import ParsedAsset, ParsedChunk, ParsedDocument

MARKUP_FILE_TYPES = {"htm", "html", "markdown", "md"}
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)]\((?P<target>[^)\s]+)(?:\s+[^)]*)?\)")
HTML_IMAGE_DATA_URI_PATTERN = re.compile(
    r"(?P<prefix><img\b[^>]*\bsrc\s*=\s*[\"'])(?P<src>data:image/[^\"']+)(?P<suffix>[\"'])",
    flags=re.IGNORECASE,
)
DATA_IMAGE_PATTERN = re.compile(
    r"^data:(?P<content_type>image/[A-Za-z0-9.+-]+);base64,(?P<payload>.+)$",
    flags=re.DOTALL,
)
MARKDOWN_TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class DataImage:
    content_type: str
    content: bytes


def parse_markup(
    content: bytes,
    *,
    file_type: str,
    source_name: str | None = None,
) -> ParsedDocument:
    """Parse Markdown or HTML into structured chunks and extracted embedded images."""

    normalized_type = file_type.lower().lstrip(".")
    if normalized_type in {"md", "markdown"}:
        return parse_markdown(content, file_type=normalized_type, source_name=source_name)
    if normalized_type in {"htm", "html"}:
        return parse_html(content, file_type=normalized_type, source_name=source_name)
    raise ValueError(f"Unsupported markup document type: {normalized_type}")


def parse_markdown(
    content: bytes,
    *,
    file_type: str = "md",
    source_name: str | None = None,
) -> ParsedDocument:
    """Parse Markdown into heading-aware chunks and image assets."""

    text = content.decode("utf-8", errors="replace")
    rewritten_text, assets = extract_markdown_data_uri_assets(text, source_name)
    chunks = markdown_blocks_to_chunks(rewritten_text)
    return ParsedDocument(
        text=rewritten_text,
        metadata={
            "parser": "markup",
            "file_type": file_type,
            "markup_format": "markdown",
            "embedded_image_count": len(assets),
        },
        assets=assets,
        chunks=chunks,
    )


def parse_html(
    content: bytes,
    *,
    file_type: str = "html",
    source_name: str | None = None,
) -> ParsedDocument:
    """Parse HTML into structural chunks and image assets."""

    html = content.decode("utf-8", errors="replace")
    rewritten_html, assets = extract_html_data_uri_assets(html, source_name)
    parser = StructuredHtmlParser()
    parser.feed(rewritten_html)
    parser.close()
    return ParsedDocument(
        text=parser.rendered_html(),
        metadata={
            "parser": "markup",
            "file_type": file_type,
            "markup_format": "html",
            "embedded_image_count": len(assets),
        },
        assets=assets,
        chunks=parser.chunks,
    )


def extract_markdown_data_uri_assets(
    text: str,
    source_name: str | None,
) -> tuple[str, list[ParsedAsset]]:
    """Replace Markdown data URI images with extracted asset paths."""

    assets: list[ParsedAsset] = []

    def replace(match: re.Match[str]) -> str:
        image = parse_data_image(match.group("target"))
        if image is None:
            return match.group(0)
        source_path = data_image_source_path(source_name, len(assets) + 1, image.content_type)
        assets.append(
            ParsedAsset(
                source_path=source_path,
                content=image.content,
                content_type=image.content_type,
                metadata={"aliases": [source_path, f"./{source_path}"]},
            )
        )
        return f"![{match.group('alt')}]({source_path})"

    return MARKDOWN_IMAGE_PATTERN.sub(replace, text), assets


def extract_html_data_uri_assets(
    html: str,
    source_name: str | None,
) -> tuple[str, list[ParsedAsset]]:
    """Replace HTML img data URI values with extracted asset paths."""

    assets: list[ParsedAsset] = []

    def replace(match: re.Match[str]) -> str:
        image = parse_data_image(match.group("src"))
        if image is None:
            return match.group(0)
        source_path = data_image_source_path(source_name, len(assets) + 1, image.content_type)
        assets.append(
            ParsedAsset(
                source_path=source_path,
                content=image.content,
                content_type=image.content_type,
                metadata={"aliases": [source_path, f"./{source_path}"]},
            )
        )
        return f"{match.group('prefix')}{source_path}{match.group('suffix')}"

    return HTML_IMAGE_DATA_URI_PATTERN.sub(replace, html), assets


def parse_data_image(value: str) -> DataImage | None:
    """Decode a base64 image data URI."""

    match = DATA_IMAGE_PATTERN.match(value.strip())
    if match is None:
        return None
    try:
        content = base64.b64decode(match.group("payload"), validate=True)
    except binascii.Error:
        return None
    if not content:
        return None
    return DataImage(content_type=match.group("content_type").lower(), content=content)


def data_image_source_path(source_name: str | None, index: int, content_type: str) -> str:
    """Return a stable asset path for an embedded image."""

    extension = mimetypes.guess_extension(content_type) or ".bin"
    if extension == ".jpe":
        extension = ".jpg"
    stem = Path(source_name or "document").stem.strip()
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "document"
    return f"assets/{safe_stem}-{index}{extension}"


def markdown_blocks_to_chunks(text: str) -> list[ParsedChunk]:
    """Convert Markdown blocks into parser-level structured chunks."""

    chunks: list[ParsedChunk] = []
    title_path: list[str] = []
    for block in split_markdown_blocks(text):
        chunk = markdown_block_to_chunk(block, title_path)
        if chunk is None:
            continue
        heading_level = chunk.metadata.get("heading_level")
        if isinstance(heading_level, int) and heading_level > 0:
            title_path = update_title_path(title_path, chunk.content, heading_level)
        chunks.append(chunk)
    return chunks


def split_markdown_blocks(text: str) -> list[str]:
    """Split Markdown into block-level fragments while preserving code fences."""

    blocks: list[str] = []
    current: list[str] = []
    in_fence = False
    fence_marker = ""
    for line in text.splitlines():
        fence = FENCE_PATTERN.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                if current and not current[-1].strip():
                    current.pop()
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            current.append(line)
            if not in_fence:
                flush_markdown_block(blocks, current)
            continue
        if in_fence:
            current.append(line)
            continue
        if not line.strip():
            flush_markdown_block(blocks, current)
            continue
        current.append(line)
    flush_markdown_block(blocks, current)
    return blocks


def flush_markdown_block(blocks: list[str], current: list[str]) -> None:
    """Append the current Markdown block if it has content."""

    block = "\n".join(current).strip()
    if block:
        blocks.append(block)
    current.clear()


def markdown_block_to_chunk(block: str, title_path: list[str]) -> ParsedChunk | None:
    """Convert one Markdown block into a typed parser chunk."""

    metadata: dict[str, object] = {"markup_block_type": markdown_block_type(block)}
    if title_path:
        metadata["title_path"] = list(title_path)
    heading_match = re.match(r"^(#{1,6})\s+(.+)$", block)
    if heading_match:
        heading_level = len(heading_match.group(1))
        metadata["heading_level"] = heading_level
        return ParsedChunk(content=block, metadata=metadata)
    if metadata["markup_block_type"] == "image":
        image_refs = markdown_image_refs(block)
        if image_refs:
            metadata["image_refs"] = image_refs
            metadata["image_path"] = image_refs[0]["image_path"]
            if image_refs[0].get("image_caption"):
                metadata["image_caption"] = image_refs[0]["image_caption"]
        return ParsedChunk(content=block, chunk_type="image", metadata=metadata)
    if metadata["markup_block_type"] == "table":
        return ParsedChunk(content=block, chunk_type="table", metadata=metadata)
    if metadata["markup_block_type"] == "code":
        return ParsedChunk(content=block, chunk_type="code", metadata=metadata)
    return ParsedChunk(content=block, metadata=metadata) if block.strip() else None


def markdown_block_type(block: str) -> str:
    """Return a stable Markdown block type."""

    if FENCE_PATTERN.match(block):
        return "code"
    if markdown_image_refs(block):
        return "image"
    if is_markdown_table(block):
        return "table"
    if re.match(r"^#{1,6}\s+", block):
        return "heading"
    if re.match(r"^\s*([-*+]\s+|\d+[.)]\s+)", block):
        return "list"
    return "paragraph"


def markdown_image_refs(block: str) -> list[dict[str, str]]:
    """Extract Markdown image references from one block."""

    refs: list[dict[str, str]] = []
    for match in MARKDOWN_IMAGE_PATTERN.finditer(block):
        ref = {"image_path": match.group("target").strip()}
        alt = match.group("alt").strip()
        if alt:
            ref["image_caption"] = alt
        refs.append(ref)
    return refs


def is_markdown_table(block: str) -> bool:
    """Return whether a Markdown block looks like a pipe table."""

    lines = [line for line in block.splitlines() if line.strip()]
    return len(lines) >= 2 and MARKDOWN_TABLE_SEPARATOR_PATTERN.match(lines[1]) is not None


class StructuredHtmlParser(HTMLParser):
    """Small HTML block parser that emits chunks in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[ParsedChunk] = []
        self.title_path: list[str] = []
        self.current_block: HtmlBlock | None = None
        self.skip_depth = 0
        self.table_depth = 0
        self.table_html: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if self.table_depth:
            self.table_depth += 1 if tag == "table" else 0
            self.table_html.append(render_start_tag(tag, attrs))
            return
        if tag == "table":
            self.flush_block()
            self.table_depth = 1
            self.table_html = [render_start_tag(tag, attrs)]
            return
        if tag == "img":
            self.flush_block()
            self.add_image_chunk(attrs)
            return
        if is_html_block_tag(tag):
            self.flush_block()
            self.current_block = HtmlBlock(tag=tag, attrs=dict(attrs))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if self.table_depth:
            self.table_html.append(f"</{tag}>")
            if tag == "table":
                self.table_depth -= 1
                if self.table_depth == 0:
                    self.add_table_chunk("".join(self.table_html))
                    self.table_html = []
            return
        if self.current_block and self.current_block.tag == tag:
            self.flush_block()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        if self.table_depth:
            self.table_html.append(escape(data))
            return
        if self.current_block is not None:
            self.current_block.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(unescape(f"&#{name};"))

    def close(self) -> None:
        super().close()
        self.flush_block()
        if self.table_html:
            self.add_table_chunk("".join(self.table_html))
            self.table_html = []

    def flush_block(self) -> None:
        if self.current_block is None:
            return
        text = normalize_whitespace(" ".join(self.current_block.parts))
        tag = self.current_block.tag
        self.current_block = None
        if not text:
            return
        metadata: dict[str, object] = {"markup_block_type": tag}
        if self.title_path:
            metadata["title_path"] = list(self.title_path)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading_level = int(tag[1])
            metadata["heading_level"] = heading_level
            self.title_path = update_title_path(self.title_path, text, heading_level)
        self.chunks.append(ParsedChunk(content=text, metadata=metadata))

    def add_image_chunk(self, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        source = attr_map.get("src", "").strip()
        if not source:
            return
        caption = normalize_whitespace(attr_map.get("alt", ""))
        metadata: dict[str, object] = {
            "markup_block_type": "image",
            "image_path": source,
        }
        if caption:
            metadata["image_caption"] = caption
        if self.title_path:
            metadata["title_path"] = list(self.title_path)
        self.chunks.append(
            ParsedChunk(
                content=html_image_fragment(source, caption),
                chunk_type="image",
                metadata=metadata,
            )
        )

    def add_table_chunk(self, table_html: str) -> None:
        text = table_html.strip()
        if not text:
            return
        metadata: dict[str, object] = {"markup_block_type": "table"}
        if self.title_path:
            metadata["title_path"] = list(self.title_path)
        self.chunks.append(ParsedChunk(content=text, chunk_type="table", metadata=metadata))

    def rendered_html(self) -> str:
        """Return a preview-friendly HTML fragment for parsed content."""

        fragments: list[str] = []
        for chunk in self.chunks:
            if chunk.chunk_type in {"image", "table"}:
                fragments.append(chunk.content)
                continue
            heading_level = chunk.metadata.get("heading_level")
            if isinstance(heading_level, int) and 1 <= heading_level <= 6:
                fragments.append(f"<h{heading_level}>{escape(chunk.content)}</h{heading_level}>")
            else:
                fragments.append(f"<p>{escape(chunk.content)}</p>")
        return "\n".join(fragments)


@dataclass
class HtmlBlock:
    tag: str
    attrs: dict[str, str | None]
    parts: list[str] = field(default_factory=list)


def is_html_block_tag(tag: str) -> bool:
    """Return whether a tag should start a standalone text chunk."""

    return tag in {
        "article",
        "blockquote",
        "code",
        "dd",
        "dt",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "pre",
    }


def render_start_tag(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    """Render an HTML start tag from parsed attributes."""

    rendered_attrs = "".join(
        f' {name}="{escape(value or "", quote=True)}"' for name, value in attrs
    )
    return f"<{tag}{rendered_attrs}>"


def html_image_fragment(source: str, caption: str) -> str:
    """Return a renderable HTML image fragment."""

    image = f'<img src="{escape(source, quote=True)}" alt="{escape(caption, quote=True)}">'
    if not caption:
        return image
    return f"<figure>{image}<figcaption>{escape(caption)}</figcaption></figure>"


def normalize_whitespace(value: str) -> str:
    """Collapse runs of whitespace for searchable text chunks."""

    return re.sub(r"\s+", " ", value).strip()


def update_title_path(title_path: list[str], heading_text: str, heading_level: int) -> list[str]:
    """Return the active title path after reading a heading."""

    title = re.sub(r"^#{1,6}\s+", "", heading_text.strip()).splitlines()[0].strip()
    if not title:
        return title_path
    return [*title_path[: max(heading_level - 1, 0)], title]