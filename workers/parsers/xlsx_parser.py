from __future__ import annotations

import mimetypes
import re
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from workers.parsers.base import ParsedAsset, ParsedChunk, ParsedDocument

PACKAGE_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_RELATIONSHIPS_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
MAX_XLSX_CHUNK_CHARS = 500
MAX_XLSX_CHUNK_ROWS = 100


def parse_xlsx(content: bytes, *, source_name: str | None = None) -> ParsedDocument:
    """Extract worksheet rows and embedded media from an XLSX package."""

    try:
        with ZipFile(BytesIO(content)) as archive:
            shared_strings = read_shared_strings(archive)
            sheet_infos = read_sheet_infos(archive)
            sheet_chunks: list[ParsedChunk] = []
            sheet_sections: list[str] = []
            total_rows = 0
            total_cells = 0

            for sheet_index, sheet_info in enumerate(sheet_infos, start=1):
                worksheet = read_xml(archive, sheet_info.path)
                if worksheet is None:
                    continue
                rows = read_worksheet_rows(worksheet, shared_strings)
                if not rows:
                    continue

                section_lines = [f"## {sheet_info.name}"]
                for row_number, values in rows:
                    total_rows += 1
                    total_cells += len(values)
                    section_lines.append(format_row_line(row_number, values))
                sheet_chunks.extend(build_sheet_chunks(sheet_info, sheet_index, rows))
                sheet_sections.append("\n".join(section_lines))

            assets, image_chunks = collect_xlsx_images(archive)
    except BadZipFile as exc:
        raise ValueError("Invalid XLSX file") from exc

    text_parts = [*sheet_sections, *[chunk.content for chunk in image_chunks]]
    return ParsedDocument(
        text="\n\n".join(part for part in text_parts if part),
        metadata={
            "parser": "xlsx-openxml",
            "source_name": source_name,
            "sheet_count": len(sheet_infos),
            "row_count": total_rows,
            "cell_count": total_cells,
            "image_count": len(assets),
        },
        assets=assets,
        chunks=[*sheet_chunks, *image_chunks],
    )


class SheetInfo:
    def __init__(self, name: str, path: str) -> None:
        self.name = name
        self.path = path


def read_shared_strings(archive: ZipFile) -> list[str]:
    """Read the workbook shared-string table."""

    root = read_xml(archive, "xl/sharedStrings.xml")
    if root is None:
        return []
    return [
        collapse_whitespace(text_content(item))
        for item in root.findall(f".//{{{SPREADSHEET_NS}}}si")
    ]


def read_sheet_infos(archive: ZipFile) -> list[SheetInfo]:
    """Read worksheet names and package paths from workbook relationships."""

    workbook = read_xml(archive, "xl/workbook.xml")
    if workbook is None:
        return fallback_sheet_infos(archive)

    relationships = read_relationships(archive, "xl/_rels/workbook.xml.rels")
    sheets: list[SheetInfo] = []
    for index, sheet in enumerate(workbook.findall(f".//{{{SPREADSHEET_NS}}}sheet"), start=1):
        relationship_id = sheet.attrib.get(f"{{{OFFICE_RELATIONSHIPS_NS}}}id")
        target = relationships.get(relationship_id or "")
        path = resolve_package_path("xl", target) if target else f"xl/worksheets/sheet{index}.xml"
        sheets.append(SheetInfo(sheet.attrib.get("name") or f"Sheet {index}", path))
    return sheets or fallback_sheet_infos(archive)


def fallback_sheet_infos(archive: ZipFile) -> list[SheetInfo]:
    """Return sorted worksheet paths when workbook metadata is unavailable."""

    paths = sorted(
        path
        for path in archive.namelist()
        if path.startswith("xl/worksheets/") and path.endswith(".xml")
    )
    return [SheetInfo(f"Sheet {index}", path) for index, path in enumerate(paths, start=1)]


def read_relationships(archive: ZipFile, path: str) -> dict[str, str]:
    """Read OpenXML relationship IDs to target paths."""

    root = read_xml(archive, path)
    if root is None:
        return {}
    relationships: dict[str, str] = {}
    for relationship in root.findall(f".//{{{PACKAGE_RELATIONSHIPS_NS}}}Relationship"):
        relationship_id = relationship.attrib.get("Id")
        target = relationship.attrib.get("Target")
        if relationship_id and target:
            relationships[relationship_id] = target
    return relationships


def read_worksheet_rows(
    worksheet: ElementTree.Element,
    shared_strings: list[str],
) -> list[tuple[int, list[str]]]:
    """Read non-empty rows from a worksheet XML tree."""

    rows: list[tuple[int, list[str]]] = []
    for row_index, row in enumerate(worksheet.findall(f".//{{{SPREADSHEET_NS}}}row"), start=1):
        row_number = int(row.attrib.get("r") or row_index)
        cells: dict[int, str] = {}
        next_column = 1
        for cell in row.findall(f"{{{SPREADSHEET_NS}}}c"):
            column = column_index_from_reference(cell.attrib.get("r")) or next_column
            next_column = column + 1
            value = read_cell_value(cell, shared_strings)
            if value:
                cells[column] = value
        if not cells:
            continue
        max_column = max(cells)
        values = [cells.get(column, "") for column in range(1, max_column + 1)]
        while values and values[-1] == "":
            values.pop()
        rows.append((row_number, values))
    return rows


def read_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    """Return a display string for one XLSX cell."""

    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return collapse_whitespace(text_content(cell.find(f"{{{SPREADSHEET_NS}}}is")))

    value = cell.findtext(f"{{{SPREADSHEET_NS}}}v")
    if value is None:
        return ""
    value = value.strip()
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (IndexError, ValueError):
            return value
    if cell_type == "b":
        return "TRUE" if value == "1" else "FALSE"
    return value


def collect_xlsx_images(archive: ZipFile) -> tuple[list[ParsedAsset], list[ParsedChunk]]:
    """Collect workbook media files as assets and image chunks."""

    assets: list[ParsedAsset] = []
    chunks: list[ParsedChunk] = []
    media_paths = sorted(path for path in archive.namelist() if path.startswith("xl/media/"))
    for image_index, path in enumerate(media_paths, start=1):
        extension = PurePosixPath(path).suffix.lower()
        if extension not in IMAGE_EXTENSIONS:
            continue
        content_type = mimetypes.types_map.get(extension, "application/octet-stream")
        title = f"Embedded image {image_index}"
        aliases = xlsx_image_aliases(path)
        assets.append(
            ParsedAsset(
                source_path=path,
                content=archive.read(path),
                content_type=content_type,
                metadata={"aliases": aliases},
            )
        )
        chunks.append(
            ParsedChunk(
                content=f"![{title}]({path})",
                chunk_type="image",
                metadata={
                    "image_caption": title,
                    "image_path": path,
                    "content_type": content_type,
                },
            )
        )
    return assets, chunks


def build_sheet_chunks(
    sheet_info: SheetInfo,
    sheet_index: int,
    rows: list[tuple[int, list[str]]],
) -> list[ParsedChunk]:
    """Group worksheet rows into bounded text chunks for embedding."""

    chunks: list[ParsedChunk] = []
    pending_lines: list[str] = []
    pending_start: int | None = None
    pending_end: int | None = None
    chunk_part = 1

    def flush() -> None:
        nonlocal chunk_part, pending_end, pending_lines, pending_start
        if pending_start is None or pending_end is None or not pending_lines:
            return
        chunks.append(
            ParsedChunk(
                content="\n".join([f"Sheet: {sheet_info.name}", *pending_lines]),
                chunk_type="table",
                metadata={
                    "sheet_name": sheet_info.name,
                    "sheet_index": sheet_index,
                    "sheet_path": sheet_info.path,
                    "row_start": pending_start,
                    "row_end": pending_end,
                    "row_count": len(pending_lines),
                    "chunk_part": chunk_part,
                    "heading_level": 2,
                },
            )
        )
        pending_lines = []
        pending_start = None
        pending_end = None
        chunk_part += 1

    for row_number, values in rows:
        line = format_row_line(row_number, values)
        projected_length = sum(len(item) + 1 for item in pending_lines) + len(line)
        if (
            pending_lines
            and (
                len(pending_lines) >= MAX_XLSX_CHUNK_ROWS
                or projected_length > MAX_XLSX_CHUNK_CHARS
            )
        ):
            flush()
        if pending_start is None:
            pending_start = row_number
        pending_end = row_number
        pending_lines.append(line)
    flush()
    return chunks


def xlsx_image_aliases(source_path: str) -> list[str]:
    """Return common aliases for workbook media paths."""

    aliases = [source_path, f"./{source_path}"]
    without_package_root = source_path.removeprefix("xl/")
    if without_package_root != source_path:
        aliases.extend(
            [without_package_root, f"./{without_package_root}", f"../{without_package_root}"]
        )
    return list(dict.fromkeys(aliases))


def format_row_line(row_number: int, values: list[str]) -> str:
    return f"R{row_number}: " + " | ".join(values)


def read_xml(archive: ZipFile, path: str) -> ElementTree.Element | None:
    try:
        with archive.open(path) as file:
            return ElementTree.parse(file).getroot()
    except KeyError:
        return None
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid XLSX XML part: {path}") from exc


def resolve_package_path(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath(base_dir, target))


def column_index_from_reference(reference: str | None) -> int | None:
    if not reference:
        return None
    match = re.match(r"([A-Za-z]+)", reference)
    if not match:
        return None
    index = 0
    for char in match.group(1).upper():
        index = index * 26 + ord(char) - ord("A") + 1
    return index


def text_content(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())