"""Excel source adapter for parsing XLSX and XLS spreadsheet files into row records.

Parses OpenXML (.xlsx) files directly via zipfile and ElementTree, and legacy (.xls) files
via optional xlrd. Supports sheet listing and dynamic header extraction.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from whitespace_tool.source_adapters.common import preview_payload


def _strip_namespace(tag: str) -> str:
    """Remove XML namespace prefix from an XML tag string.

    Args:
        tag: Full XML tag name.

    Returns:
        Local tag name without namespace.
    """
    return tag.rsplit("}", 1)[-1]


def _column_index(cell_ref: str) -> int:
    """Convert Excel cell reference (e.g. 'B3') into a 0-based column index.

    Args:
        cell_ref: Cell reference string.

    Returns:
        0-based column index integer.
    """
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Extract shared string table values from an XLSX archive.

    Args:
        zf: Open ZipFile object for the XLSX workbook.

    Returns:
        List of shared string values.
    """
    try:
        root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for si in root:
        text_parts = []
        for node in si.iter():
            if _strip_namespace(node.tag) == "t" and node.text:
                text_parts.append(node.text)
        values.append("".join(text_parts))
    return values


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> str:
    """Extract string value from an XLSX cell XML element.

    Args:
        cell: ElementTree cell XML element.
        shared: Shared string list.

    Returns:
        Evaluated cell string value.
    """
    cell_type = cell.attrib.get("t")
    value = ""
    for child in cell:
        if _strip_namespace(child.tag) == "v":
            value = child.text or ""
            break
        if _strip_namespace(child.tag) == "is":
            value = "".join(node.text or "" for node in child.iter() if _strip_namespace(node.tag) == "t")
            break
    if cell_type == "s" and value:
        index = int(value)
        return shared[index] if index < len(shared) else ""
    return value


def _table_from_rows(rows_as_lists: list[list[str]], record_path: str, fields_only: bool = False) -> dict:
    """Convert raw 2D row lists into structured record dictionaries with header names.

    Args:
        rows_as_lists: List of row values lists.
        record_path: Sheet name or record path identifier.

    Returns:
        Preview payload dictionary.
    """
    rows_as_lists = [row for row in rows_as_lists if any(str(value).strip() for value in row)]
    if not rows_as_lists:
        return preview_payload([], record_path)

    width = max(len(row) for row in rows_as_lists)
    header_row = rows_as_lists[0]
    headers = []
    seen: dict[str, int] = {}
    for index in range(width):
        raw_header = str(header_row[index]).strip() if index < len(header_row) else ""
        header = raw_header or f"column_{index + 1}"
        if header in seen:
            seen[header] += 1
            header = f"{header}_{seen[header]}"
        else:
            seen[header] = 1
        headers.append(header)

    rows = []
    for row in rows_as_lists[1:]:
        values = [row[index] if index < len(row) else "" for index in range(width)]
        if any(str(value).strip() for value in values):
            rows.append({headers[index]: values[index] for index in range(width)})
    return preview_payload(rows, record_path, fields_only=fields_only)


def _xlsx_sheet_map(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map sheet names to internal XML target paths inside XLSX archive.

    Args:
        zf: Open ZipFile object.

    Returns:
        Mapping of sheet name to worksheet XML path.
    """
    workbook = ElementTree.fromstring(zf.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels
    }
    sheets: dict[str, str] = {}
    for sheet in workbook.iter():
        if _strip_namespace(sheet.tag) != "sheet":
            continue
        name = sheet.attrib["name"]
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = rel_targets[rel_id]
        if not target.startswith("xl/"):
            target = f"xl/{target.lstrip('/')}"
        sheets[name] = target
    return sheets


def list_sheets(content: bytes, file_name: str = "") -> list[str]:
    """List available sheet names in an Excel file workbook.

    Args:
        content: Excel file bytes.
        file_name: Optional file name to check extension.

    Returns:
        List of sheet names.
    """
    if file_name.lower().endswith(".xls") and not file_name.lower().endswith(".xlsx"):
        try:
            import xlrd
        except ImportError as exc:
            raise RuntimeError("Install xlrd to inspect legacy .xls files.") from exc
        workbook = xlrd.open_workbook(file_contents=content)
        return workbook.sheet_names()

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return list(_xlsx_sheet_map(zf).keys())


def _preview_xls(content: bytes, sheet_name: str | None, fields_only: bool = False) -> dict:
    """Preview legacy .xls file using xlrd.

    Args:
        content: File bytes.
        sheet_name: Target sheet name.
        fields_only: If True, returns fields and sample rows without processing all rows.

    Returns:
        Preview payload dictionary.
    """
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("Install xlrd to preview legacy .xls files.") from exc

    workbook = xlrd.open_workbook(file_contents=content)
    sheet = workbook.sheet_by_name(sheet_name) if sheet_name else workbook.sheet_by_index(0)
    if sheet.nrows == 0:
        return preview_payload([], sheet.name)
    rows_as_lists = [sheet.row_values(row_index) for row_index in range(sheet.nrows)]
    return _table_from_rows(rows_as_lists, sheet.name, fields_only=fields_only)


def preview(content: bytes, record_path: str | None = None, file_name: str = "", fields_only: bool = False) -> dict:
    """Parse Excel content bytes and return a preview payload of rows.

    Args:
        content: Excel file bytes.
        record_path: Target sheet name.
        file_name: Excel file name.
        fields_only: If True, returns fields and sample rows without full processing.

    Returns:
        Preview payload dictionary containing extracted records and metadata.
    """
    if file_name.lower().endswith(".xls") and not file_name.lower().endswith(".xlsx"):
        return _preview_xls(content, record_path, fields_only=fields_only)

    rows_as_lists: list[list[str]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        shared = _shared_strings(zf)
        sheets = _xlsx_sheet_map(zf)
        selected_sheet = record_path or next(iter(sheets))
        sheet_path = sheets.get(selected_sheet, selected_sheet)
        if not sheet_path.startswith("xl/"):
            sheet_path = f"xl/worksheets/{sheet_path}"
        if not sheet_path.endswith(".xml"):
            sheet_path = f"{sheet_path}.xml"
        sheet = ElementTree.fromstring(zf.read(sheet_path))
        for row in sheet.iter():
            if _strip_namespace(row.tag) != "row":
                continue
            values: dict[int, str] = {}
            for cell in row:
                if _strip_namespace(cell.tag) != "c":
                    continue
                values[_column_index(cell.attrib.get("r", "A1"))] = _cell_value(cell, shared)
            if values:
                width = max(values) + 1
                rows_as_lists.append([values.get(index, "") for index in range(width)])

    return _table_from_rows(rows_as_lists, selected_sheet, fields_only=fields_only)

