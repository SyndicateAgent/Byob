from io import BytesIO
from pathlib import PurePosixPath
from re import sub

from PIL import Image, UnidentifiedImageError

from workers.parsers.base import ParsedAsset, ParsedChunk, ParsedDocument

IMAGE_FILE_TYPES = {"jpg", "jpeg", "png"}
IMAGE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
IMAGE_FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
}


def parse_image(
    content: bytes,
    *,
    file_type: str | None = None,
    source_name: str | None = None,
) -> ParsedDocument:
    """Parse a standalone JPEG/PNG upload into a retrievable visual document."""

    normalized_type = normalize_image_type(file_type)
    expected_content_type = IMAGE_CONTENT_TYPES.get(normalized_type)
    if expected_content_type is None:
        raise ValueError(f"Unsupported image type: {normalized_type}")

    try:
        with Image.open(BytesIO(content)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Invalid image document") from exc

    content_type = IMAGE_FORMAT_CONTENT_TYPES.get(image_format)
    if content_type is None:
        raise ValueError(f"Unsupported image format: {image_format or 'unknown'}")

    source_path = image_source_path(source_name, normalized_type)
    title = image_title(source_path)
    text = "\n\n".join(
        [
            f"# {title}",
            f"![{escape_markdown_alt(title)}]({source_path})",
            f"Standalone image document. Format: {image_format}; dimensions: {width}x{height}.",
        ]
    )

    aliases = [source_path, f"./{source_path}"]
    return ParsedDocument(
        text=text,
        metadata={
            "parser": "image",
            "file_type": normalized_type,
            "image_format": image_format,
            "content_type": content_type,
            "width": width,
            "height": height,
        },
        assets=[
            ParsedAsset(
                source_path=source_path,
                content=content,
                content_type=content_type,
                asset_type="image",
                metadata={
                    "aliases": aliases,
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                },
            )
        ],
        chunks=[
            ParsedChunk(
                content=text,
                chunk_type="image",
                metadata={
                    "image_caption": title,
                    "image_path": source_path,
                    "image_format": image_format,
                    "width": width,
                    "height": height,
                },
            )
        ],
    )


def normalize_image_type(file_type: str | None) -> str:
    """Normalize a file extension for standalone image parsing."""

    return (file_type or "png").lower().lstrip(".")


def image_source_path(source_name: str | None, file_type: str) -> str:
    """Return a stable source path used for Markdown asset rewriting."""

    extension = "jpg" if file_type == "jpeg" else file_type
    raw_name = source_name or f"image.{extension}"
    filename = PurePosixPath(raw_name.replace("\\", "/")).name.strip()
    if not filename:
        filename = f"image.{extension}"
    if "." not in filename:
        filename = f"{filename}.{extension}"
    filename = sub(r"[\r\n\t]", "_", filename)
    return filename.translate(str.maketrans({character: "_" for character in "()[]<>"}))


def image_title(source_path: str) -> str:
    """Return a compact human-readable title for the image chunk."""

    stem = PurePosixPath(source_path).stem.strip()
    return stem.replace("_", " ").replace("-", " ") or "Uploaded image"


def escape_markdown_alt(value: str) -> str:
    """Escape Markdown image alt text delimiters."""

    return value.replace("\\", "\\\\").replace("]", "\\]")
