from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from whitespace_tool.source_preview.common import preview_payload


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
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
        return shared[int(value)]
    return value


def _xlsx_sheet_map(zf: zipfile.ZipFile) -> dict[str, str]:
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
    if file_name.lower().endswith(".xls") and not file_name.lower().endswith(".xlsx"):
        try:
            import xlrd
        except ImportError as exc:
            raise RuntimeError("Install xlrd to inspect legacy .xls files.") from exc
        workbook = xlrd.open_workbook(file_contents=content)
        return workbook.sheet_names()

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        return list(_xlsx_sheet_map(zf).keys())


def _preview_xls(content: bytes, sheet_name: str | None) -> dict:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("Install xlrd to preview legacy .xls files.") from exc

    workbook = xlrd.open_workbook(file_contents=content)
    sheet = workbook.sheet_by_name(sheet_name) if sheet_name else workbook.sheet_by_index(0)
    if sheet.nrows == 0:
        return preview_payload([], sheet.name)
    headers = [str(value).strip() or f"column_{index + 1}" for index, value in enumerate(sheet.row_values(0))]
    rows = []
    for row_index in range(1, sheet.nrows):
        values = sheet.row_values(row_index)
        rows.append({headers[index]: values[index] if index < len(values) else "" for index in range(len(headers))})
    return preview_payload(rows, sheet.name)


def preview(content: bytes, record_path: str | None = None, file_name: str = "") -> dict:
    if file_name.lower().endswith(".xls") and not file_name.lower().endswith(".xlsx"):
        return _preview_xls(content, record_path)

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

    if not rows_as_lists:
        return preview_payload([], sheet_name)
    headers = [header or f"column_{index + 1}" for index, header in enumerate(rows_as_lists[0])]
    rows = [
        {headers[index]: value for index, value in enumerate(row)}
        for row in rows_as_lists[1:]
    ]
    return preview_payload(rows, selected_sheet)
