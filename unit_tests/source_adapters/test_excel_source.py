"""Real-behavior tests for the hand-rolled xlsx/xls adapter.

excel_source.py parses .xlsx by unzipping it and walking the raw
spreadsheetml XML itself (no openpyxl at read time), and parses legacy .xls
via the optional xlrd dependency. These tests build minimal-but-real xlsx
byte content (a genuine zip containing xl/workbook.xml,
xl/_rels/workbook.xml.rels, xl/worksheets/sheetN.xml and, where relevant,
xl/sharedStrings.xml) so the adapter's own XML walking is exercised end to
end, plus one round trip against openpyxl's real writer output as the
strongest possible check that the hand-rolled parser matches what a real
library actually emits.
"""

from __future__ import annotations

import io
import unittest
import zipfile
from unittest.mock import patch

from whitespace_tool.source_adapters import excel_source

XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

WORKBOOK_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_letter(index: int) -> str:
    """0-based column index -> spreadsheet column letters (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _cell_xml(col: int, row: int, value: str | None, cell_type: str | None) -> str:
    ref = f"{_col_letter(col)}{row}"
    if value is None:
        return ""
    if cell_type == "inlineStr":
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
    if cell_type == "s":
        return f'<c r="{ref}" t="s"><v>{value}</v></c>'
    return f'<c r="{ref}"><v>{value}</v></c>'


def _row_xml(row_number: int, cells: list) -> str:
    """cells: list of (value, cell_type) tuples, or None to skip a cell (ragged rows)."""
    parts = []
    for col, cell in enumerate(cells):
        if cell is None:
            continue
        value, cell_type = cell
        parts.append(_cell_xml(col, row_number, value, cell_type))
    return f'<row r="{row_number}">' + "".join(parts) + "</row>"


def _sheet_xml(rows_xml: list) -> str:
    return (
        XML_HEADER
        + f'<worksheet xmlns="{WORKBOOK_NS}"><sheetData>'
        + "".join(rows_xml)
        + "</sheetData></worksheet>"
    )


def _workbook_xml(sheet_names: list) -> str:
    sheets = "".join(
        f'<sheet name="{name}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, name in enumerate(sheet_names)
    )
    return (
        XML_HEADER
        + f'<workbook xmlns="{WORKBOOK_NS}" xmlns:r="{REL_NS}"><sheets>{sheets}</sheets></workbook>'
    )


def _rels_xml(sheet_count: int) -> str:
    rels = "".join(
        f'<Relationship Id="rId{i + 1}" '
        f'Type="{REL_NS}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
        for i in range(sheet_count)
    )
    return XML_HEADER + f'<Relationships xmlns="{PKG_REL_NS}">{rels}</Relationships>'


def _shared_strings_xml(strings: list) -> str:
    items = "".join(f"<si><t>{value}</t></si>" for value in strings)
    return (
        XML_HEADER
        + f'<sst xmlns="{WORKBOOK_NS}" count="{len(strings)}" uniqueCount="{len(strings)}">{items}</sst>'
    )


def build_xlsx(sheets: dict, shared_strings: list | None = None) -> bytes:
    """Build a minimal-but-real xlsx zip.

    sheets: {sheet_name: [row_xml, ...]} in the order they should appear in
    the workbook. Only the parts excel_source.py actually reads are written
    (no [Content_Types].xml / docProps, since the adapter never opens them).
    """
    sheet_names = list(sheets.keys())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("xl/workbook.xml", _workbook_xml(sheet_names))
        zf.writestr("xl/_rels/workbook.xml.rels", _rels_xml(len(sheet_names)))
        for index, name in enumerate(sheet_names):
            zf.writestr(f"xl/worksheets/sheet{index + 1}.xml", _sheet_xml(sheets[name]))
        if shared_strings is not None:
            zf.writestr("xl/sharedStrings.xml", _shared_strings_xml(shared_strings))
    return buffer.getvalue()


class ListSheetsTests(unittest.TestCase):
    def test_lists_sheet_names_in_workbook_order(self) -> None:
        content = build_xlsx(
            {
                "Locations": [_row_xml(1, [("Name", None), ("City", None)])],
                "Notes": [_row_xml(1, [("Text", None)])],
            }
        )
        self.assertEqual(excel_source.list_sheets(content, "brand.xlsx"), ["Locations", "Notes"])

    def test_single_sheet_workbook(self) -> None:
        content = build_xlsx({"Sheet1": [_row_xml(1, [("A", None)])]})
        self.assertEqual(excel_source.list_sheets(content, "brand.xlsx"), ["Sheet1"])


class PreviewBasicTableTests(unittest.TestCase):
    def test_multi_row_multi_column_sheet_parses_headers_and_rows(self) -> None:
        rows = [
            _row_xml(1, [("Name", None), ("City", None), ("Zip", None)]),
            _row_xml(2, [("Store A", None), ("Austin", None), ("78701", None)]),
            _row_xml(3, [("Store B", None), ("Dallas", None), ("75201", None)]),
        ]
        content = build_xlsx({"Sheet1": rows})

        result = excel_source.preview(content, file_name="brand.xlsx")

        self.assertEqual(result["fields"], ["City", "Name", "Zip"])
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(
            result["rows"],
            [
                {"Name": "Store A", "City": "Austin", "Zip": "78701"},
                {"Name": "Store B", "City": "Dallas", "Zip": "75201"},
            ],
        )

    def test_default_sheet_is_first_sheet_when_no_record_path_given(self) -> None:
        content = build_xlsx(
            {
                "First": [_row_xml(1, [("A", None)]), _row_xml(2, [("1", None)])],
                "Second": [_row_xml(1, [("B", None)]), _row_xml(2, [("2", None)])],
            }
        )
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(result["record_path"], "First")
        self.assertEqual(result["rows"], [{"A": "1"}])

    def test_record_path_selects_named_sheet(self) -> None:
        content = build_xlsx(
            {
                "First": [_row_xml(1, [("A", None)]), _row_xml(2, [("1", None)])],
                "Second": [_row_xml(1, [("B", None)]), _row_xml(2, [("2", None)])],
            }
        )
        result = excel_source.preview(content, record_path="Second", file_name="brand.xlsx")
        self.assertEqual(result["record_path"], "Second")
        self.assertEqual(result["rows"], [{"B": "2"}])

    def test_empty_sheet_returns_empty_preview_payload(self) -> None:
        content = build_xlsx({"Sheet1": []})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["fields"], [])
        self.assertEqual(result["record_count"], 0)

    def test_blank_rows_interspersed_are_dropped(self) -> None:
        # Row 3 is entirely blank cells (all-whitespace values) - the adapter
        # filters rows where every value is blank, both for the header/width
        # computation and for the emitted data rows.
        rows = [
            _row_xml(1, [("Name", None), ("City", None)]),
            _row_xml(2, [("Store A", None), ("Austin", None)]),
            _row_xml(3, [("  ", None), ("", None)]),
            _row_xml(4, [("Store B", None), ("Dallas", None)]),
        ]
        content = build_xlsx({"Sheet1": rows})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(
            result["rows"],
            [
                {"Name": "Store A", "City": "Austin"},
                {"Name": "Store B", "City": "Dallas"},
            ],
        )
        self.assertEqual(result["record_count"], 2)

    def test_ragged_rows_shorter_than_header_width_fill_blank(self) -> None:
        rows = [
            _row_xml(1, [("Name", None), ("City", None), ("Zip", None)]),
            # Row 2 only has 2 of 3 columns present (missing trailing cell).
            _row_xml(2, [("Store A", None), ("Austin", None)]),
        ]
        content = build_xlsx({"Sheet1": rows})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(result["rows"], [{"Name": "Store A", "City": "Austin", "Zip": ""}])

    def test_row_missing_leading_cell_still_aligns_by_column_ref(self) -> None:
        # Cell refs (not positional order) drive column placement: row 2 skips
        # column A entirely (e.g. Excel omitted an empty leading cell), and the
        # adapter must still place "Austin" under City, not shift it to Name.
        rows = [
            _row_xml(1, [("Name", None), ("City", None)]),
            f'<row r="2">{_cell_xml(1, 2, "Austin", None)}</row>',
        ]
        content = build_xlsx({"Sheet1": rows})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(result["rows"], [{"Name": "", "City": "Austin"}])


class PreviewDuplicateHeaderTests(unittest.TestCase):
    def test_duplicate_header_names_are_disambiguated(self) -> None:
        # First occurrence of "Phone" keeps its name; each later duplicate
        # gets a running "_2", "_3" suffix (see excel_source._table_from_rows).
        rows = [
            _row_xml(1, [("Phone", None), ("Phone", None), ("Phone", None)]),
            _row_xml(2, [("111", None), ("222", None), ("333", None)]),
        ]
        content = build_xlsx({"Sheet1": rows})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(sorted(result["fields"]), ["Phone", "Phone_2", "Phone_3"])
        self.assertEqual(result["rows"], [{"Phone": "111", "Phone_2": "222", "Phone_3": "333"}])

    def test_blank_header_cells_get_generated_column_names(self) -> None:
        rows = [
            _row_xml(1, [("Name", None), ("", None), ("Zip", None)]),
            _row_xml(2, [("Store A", None), ("Extra", None), ("78701", None)]),
        ]
        content = build_xlsx({"Sheet1": rows})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(sorted(result["fields"]), ["Name", "Zip", "column_2"])
        self.assertEqual(result["rows"][0]["column_2"], "Extra")


class PreviewSharedAndInlineStringTests(unittest.TestCase):
    def test_shared_strings_and_inline_strings_both_resolve(self) -> None:
        # Column A cells are shared-string references (t="s", index into
        # sharedStrings.xml); column B cells are inline strings (t="inlineStr").
        shared = ["Name", "Store A", "Store B"]
        rows = [
            _row_xml(1, [("0", "s"), ("City", "inlineStr")]),
            _row_xml(2, [("1", "s"), ("Austin", "inlineStr")]),
            _row_xml(3, [("2", "s"), ("Dallas", "inlineStr")]),
        ]
        content = build_xlsx({"Sheet1": rows}, shared_strings=shared)
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(
            result["rows"],
            [{"Name": "Store A", "City": "Austin"}, {"Name": "Store B", "City": "Dallas"}],
        )

    def test_shared_string_index_out_of_range_resolves_to_empty_string(self) -> None:
        # _cell_value defensively returns "" rather than raising IndexError
        # when a shared-string index is out of bounds. A second populated
        # column keeps the row from being dropped entirely by the
        # all-blank-row filter, isolating just the out-of-range cell's value.
        rows = [
            _row_xml(1, [("Name", None), ("City", None)]),
            _row_xml(2, [("99", "s"), ("Austin", None)]),
        ]
        content = build_xlsx({"Sheet1": rows}, shared_strings=["OnlyOne"])
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(result["rows"], [{"Name": "", "City": "Austin"}])

    def test_no_shared_strings_part_present_is_tolerated(self) -> None:
        content = build_xlsx({"Sheet1": [_row_xml(1, [("Name", None)]), _row_xml(2, [("A", None)])]})
        result = excel_source.preview(content, file_name="brand.xlsx")
        self.assertEqual(result["rows"], [{"Name": "A"}])


class PreviewFieldsOnlyTests(unittest.TestCase):
    def _build_wide_sheet(self, data_row_count: int) -> bytes:
        rows = [_row_xml(1, [("Name", None), ("City", None)])]
        for i in range(data_row_count):
            rows.append(_row_xml(i + 2, [(f"Store {i}", None), ("Austin", None)]))
        return build_xlsx({"Sheet1": rows})

    def test_fields_only_caps_the_xlsx_sample_at_fifty_rows(self) -> None:
        """Regression test (2026-09-10): _table_from_rows() has real
        fields_only=True handling (cap the sample at 50 rows via
        rows_as_lists[1:51], report the true record_count separately) - the
        code comment right above it even says "Return a small sample for the
        mapper preview while keeping the full file out of the fast parse
        response." That logic was exercised correctly for legacy .xls
        through _preview_xls() (which does pass fields_only through), but
        the top-level xlsx preview() never forwarded its own fields_only
        argument to _table_from_rows() at all - excel_source.py's xlsx path
        was a bare `return _table_from_rows(rows_as_lists, selected_sheet)`,
        silently defaulting to False. Every xlsx "parse for discovery" call
        (the mapper's fast preview, per CLAUDE.md's "parse samples inspect
        at most 50 records" data-flow contract) actually parsed and returned
        the ENTIRE file, exactly like a full save-path parse - for a large
        real-world upload this defeated the whole point of the fast/sampled
        discovery path. Fixed by forwarding fields_only through; this test
        pins the fix.
        """
        content = self._build_wide_sheet(60)
        result = excel_source.preview(content, file_name="brand.xlsx", fields_only=True)
        self.assertEqual(len(result["rows"]), 50)
        self.assertEqual(result["record_count"], 60)

    def test_fields_only_with_fewer_than_fifty_rows_returns_all_of_them(self) -> None:
        content = self._build_wide_sheet(5)
        result = excel_source.preview(content, file_name="brand.xlsx", fields_only=True)
        self.assertEqual(len(result["rows"]), 5)
        self.assertEqual(result["record_count"], 5)

    def test_full_preview_row_list_is_not_capped_at_fifty(self) -> None:
        # fields_only=False (the save path) must not silently truncate real
        # data - only the mapper's field-discovery preview does that.
        content = self._build_wide_sheet(60)
        result = excel_source.preview(content, file_name="brand.xlsx", fields_only=False)
        self.assertEqual(len(result["rows"]), 60)
        self.assertEqual(result["record_count"], 60)
        # preview_rows (UI sample) is still capped at preview_payload's limit=25.
        self.assertEqual(len(result["preview_rows"]), 25)


class OpenpyxlRoundTripTests(unittest.TestCase):
    """Strongest possible check: parse real bytes written by a real library.

    A first pass here suspected a second real bug (preview() crashing on
    openpyxl-written absolute OOXML relationship Targets, e.g.
    "/xl/worksheets/sheet1.xml") - directly verified against real openpyxl
    output afterward and it does NOT reproduce: preview() parses these files
    correctly, `_normalize_xlsx_part_path()` already strips the leading "/"
    before the "xl/" prefix check. `fields` in the payload comes back
    alphabetically sorted rather than in column order - that's
    collect_fields()'s existing, deliberate, shared behavior across every
    source adapter (common.py, sorted(set(...))), not something specific to
    Excel or a bug, so these tests assert the sorted order rather than
    column order.
    """

    def test_list_sheets_works_against_real_openpyxl_output(self) -> None:
        openpyxl = __import__("openpyxl")
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Locations"
        sheet.append(["Name", "City", "Zip"])
        other = workbook.create_sheet("Extra")
        other.append(["Note"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        self.assertEqual(excel_source.list_sheets(buffer.getvalue(), "brand.xlsx"), ["Locations", "Extra"])

    def test_preview_parses_real_openpyxl_output_with_absolute_relationship_targets(self) -> None:
        """openpyxl writes absolute OOXML part targets such as
        `/xl/worksheets/sheet1.xml`; those must resolve from the package root,
        not become `xl/xl/worksheets/sheet1.xml`."""
        openpyxl = __import__("openpyxl")
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Locations"
        sheet.append(["Name", "City"])
        sheet.append(["Store A", "Austin"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        result = excel_source.preview(buffer.getvalue(), file_name="brand.xlsx")

        self.assertEqual(result["record_path"], "Locations")
        self.assertEqual(result["fields"], ["City", "Name"])  # collect_fields() sorts
        self.assertEqual(result["rows"], [{"Name": "Store A", "City": "Austin"}])

    def test_minimal_repro_absolute_relationship_target_breaks_sheet_path_resolution(self) -> None:
        """Same bug as above, isolated to a minimal hand-built fixture so the
        exact defect (not just "openpyxl output crashes") is pinned down."""
        sheet_xml = _sheet_xml([_row_xml(1, [("Name", None)]), _row_xml(2, [("A", None)])])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("xl/workbook.xml", _workbook_xml(["Sheet1"]))
            # Absolute Target (leading "/"), same shape openpyxl writes.
            zf.writestr(
                "xl/_rels/workbook.xml.rels",
                XML_HEADER
                + f'<Relationships xmlns="{PKG_REL_NS}">'
                f'<Relationship Id="rId1" Type="{REL_NS}/worksheet" Target="/xl/worksheets/sheet1.xml"/>'
                "</Relationships>",
            )
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        result = excel_source.preview(buffer.getvalue(), file_name="brand.xlsx")

        self.assertEqual(result["fields"], ["Name"])
        self.assertEqual(result["rows"], [{"Name": "A"}])


class XlsLegacyTests(unittest.TestCase):
    """Legacy .xls support via the optional xlrd dependency.

    No writer library for the legacy BIFF .xls binary format (e.g. xlwt) is
    installed in this environment, so real .xls fixture bytes can't be
    generated here. xlrd itself IS installed, so rather than skip this path
    entirely, these tests mock xlrd.open_workbook's return value with a
    minimal fake workbook object that implements exactly the surface
    excel_source.py calls (sheet_names/sheet_by_name/sheet_by_index/nrows/
    row_values) - this still exercises excel_source's own branching and
    _table_from_rows reuse for the .xls path for real, it just doesn't
    exercise xlrd's own binary parser.
    """

    class _FakeSheet:
        def __init__(self, name: str, rows: list) -> None:
            self.name = name
            self._rows = rows
            self.nrows = len(rows)

        def row_values(self, index: int) -> list:
            return self._rows[index]

    class _FakeWorkbook:
        def __init__(self, sheets: dict) -> None:
            self._sheets = {name: XlsLegacyTests._FakeSheet(name, rows) for name, rows in sheets.items()}
            self._order = list(sheets.keys())

        def sheet_names(self) -> list:
            return list(self._order)

        def sheet_by_name(self, name: str):
            return self._sheets[name]

        def sheet_by_index(self, index: int):
            return self._sheets[self._order[index]]

    def test_list_sheets_for_xls_delegates_to_xlrd(self) -> None:
        fake_workbook = self._FakeWorkbook({"Sheet1": [["Name"]], "Sheet2": [["Name"]]})
        with patch("xlrd.open_workbook", return_value=fake_workbook) as mocked:
            names = excel_source.list_sheets(b"fake-xls-bytes", "brand.xls")
        self.assertEqual(names, ["Sheet1", "Sheet2"])
        mocked.assert_called_once_with(file_contents=b"fake-xls-bytes")

    def test_preview_xls_uses_first_sheet_by_default(self) -> None:
        fake_workbook = self._FakeWorkbook(
            {"Sheet1": [["Name", "City"], ["Store A", "Austin"]]}
        )
        with patch("xlrd.open_workbook", return_value=fake_workbook):
            result = excel_source.preview(b"fake-xls-bytes", file_name="brand.xls")
        self.assertEqual(result["record_path"], "Sheet1")
        self.assertEqual(result["rows"], [{"Name": "Store A", "City": "Austin"}])

    def test_preview_xls_selects_named_sheet(self) -> None:
        fake_workbook = self._FakeWorkbook(
            {
                "Sheet1": [["Name"], ["A"]],
                "Sheet2": [["City"], ["Austin"]],
            }
        )
        with patch("xlrd.open_workbook", return_value=fake_workbook):
            result = excel_source.preview(b"fake-xls-bytes", record_path="Sheet2", file_name="brand.xls")
        self.assertEqual(result["rows"], [{"City": "Austin"}])

    def test_preview_xls_empty_sheet_returns_empty_payload(self) -> None:
        fake_workbook = self._FakeWorkbook({"Sheet1": []})
        with patch("xlrd.open_workbook", return_value=fake_workbook):
            result = excel_source.preview(b"fake-xls-bytes", file_name="brand.xls")
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["record_count"], 0)

    def test_xls_extension_check_does_not_misfire_on_xlsx(self) -> None:
        # ".xlsx".endswith(".xls") is True in a naive check - excel_source
        # guards against that explicitly, so a real .xlsx file name must NOT
        # be routed into the xlrd/.xls branch.
        content = build_xlsx({"Sheet1": [_row_xml(1, [("Name", None)]), _row_xml(2, [("A", None)])]})
        with patch("xlrd.open_workbook") as mocked:
            excel_source.preview(content, file_name="brand.xlsx")
        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
