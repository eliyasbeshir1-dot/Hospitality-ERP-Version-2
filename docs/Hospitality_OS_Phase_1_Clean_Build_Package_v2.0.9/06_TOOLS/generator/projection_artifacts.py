#!/usr/bin/env python3
"""Deterministic standard-library writers for generator projection artifacts."""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _zip_write(archive: zipfile.ZipFile, name: str, data: str | bytes) -> None:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (0o100644 & 0xFFFF) << 16
    archive.writestr(info, payload)


def _xml_text(value: object) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or ""))
    return html.escape(text, quote=False)


def _column(index: int) -> str:
    value = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        value = chr(65 + remainder) + value
    return value


def write_xlsx(path: Path, sheets: list[tuple]) -> None:
    """Write a deterministic, styled XLSX with no formulas or volatile metadata.

    Each sheet is ``(name, rows)`` or ``(name, rows, options)``. Supported options are
    ``header_row`` (1-based), ``freeze_row``, ``title_merge`` and ``autofilter``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    workbook_sheets = []
    relationships = []
    worksheets: list[tuple[str, str]] = []
    for sheet_index, sheet_spec in enumerate(sheets, start=1):
        name, rows = sheet_spec[:2]
        options = sheet_spec[2] if len(sheet_spec) > 2 else {}
        header_row = int(options.get("header_row", 1))
        freeze_row = int(options.get("freeze_row", header_row))
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{sheet_index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        workbook_sheets.append(
            f'<sheet name="{html.escape(name, quote=True)}" sheetId="{sheet_index}" r:id="rId{sheet_index}"/>'
        )
        relationships.append(
            f'<Relationship Id="rId{sheet_index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{sheet_index}.xml"/>'
        )
        xml_rows = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row):
                reference = f"{_column(column_index)}{row_index}"
                style = 3 if options.get("title_merge") and row_index == 1 else 1 if row_index == header_row else 2 if row_index > header_row and row_index % 2 == 0 else 0
                if value is None or value == "":
                    cells.append(f'<c r="{reference}" s="{style}"/>')
                elif isinstance(value, bool):
                    cells.append(f'<c r="{reference}" s="{style}" t="b"><v>{1 if value else 0}</v></c>')
                elif isinstance(value, (int, float)):
                    cells.append(f'<c r="{reference}" s="{style}"><v>{value}</v></c>')
                else:
                    cells.append(
                        f'<c r="{reference}" s="{style}" t="inlineStr"><is><t xml:space="preserve">'
                        f'{_xml_text(value)}</t></is></c>'
                    )
            xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        column_count = max((len(row) for row in rows), default=1)
        widths = []
        for column_index in range(column_count):
            observed = max((len(str(row[column_index])) for row in rows[:80] if column_index < len(row) and row[column_index] is not None), default=8)
            width = min(42, max(10, observed + 2))
            widths.append(f'<col min="{column_index + 1}" max="{column_index + 1}" width="{width}" customWidth="1"/>')
        pane = f'<pane ySplit="{freeze_row}" topLeftCell="A{freeze_row + 1}" activePane="bottomLeft" state="frozen"/>' if freeze_row else ''
        merge = f'<mergeCells count="1"><mergeCell ref="{options["title_merge"]}"/></mergeCells>' if options.get("title_merge") else ''
        autofilter = f'<autoFilter ref="{options["autofilter"]}"/>' if options.get("autofilter") else ''
        dimension = f'A1:{_column(column_count - 1)}{max(1, len(rows))}'
        worksheets.append(
            (
                f"xl/worksheets/sheet{sheet_index}.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<dimension ref="{dimension}"/><sheetViews><sheetView showGridLines="0" workbookViewId="0">{pane}</sheetView></sheetViews>'
                f'<cols>{"".join(widths)}</cols><sheetData>{"".join(xml_rows)}</sheetData>{autofilter}{merge}</worksheet>',
            )
        )
    content_types.append("</Types>")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(workbook_sheets)}</sheets></workbook>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(relationships)}<Relationship Id="rId{len(sheets) + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3"><font><sz val="11"/><name val="Carlito"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Carlito"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="18"/><name val="Carlito"/></font></fonts>'
        '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF17324D"/><bgColor indexed="64"/></patternFill></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFD9EEF7"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="2"><border/><border><left style="thin"><color rgb="FFD9E2E8"/></left><right style="thin"><color rgb="FFD9E2E8"/></right><top style="thin"><color rgb="FFD9E2E8"/></top><bottom style="thin"><color rgb="FFD9E2E8"/></bottom></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="4">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        _zip_write(archive, "[Content_Types].xml", "".join(content_types))
        _zip_write(archive, "_rels/.rels", root_rels)
        _zip_write(archive, "xl/workbook.xml", workbook)
        _zip_write(archive, "xl/_rels/workbook.xml.rels", workbook_rels)
        _zip_write(archive, "xl/styles.xml", styles)
        for name, payload in worksheets:
            _zip_write(archive, name, payload)


def write_docx(path: Path, title: str, markdown: str) -> None:
    """Write a deterministic, readable DOCX projection of the master Markdown."""
    path.parent.mkdir(parents=True, exist_ok=True)
    paragraphs = [title, ""] + markdown.splitlines()
    body = []
    for line in paragraphs:
        body.append(
            '<w:p><w:r><w:t xml:space="preserve">'
            f'{_xml_text(line)}</w:t></w:r></w:p>'
        )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body>{"".join(body)}<w:sectPr/></w:body></w:document>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '</Types>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        _zip_write(archive, "[Content_Types].xml", content_types)
        _zip_write(archive, "_rels/.rels", relationships)
        _zip_write(archive, "word/document.xml", document)


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path: Path, title: str, markdown: str) -> None:
    """Write a deterministic uncompressed text PDF without external dependencies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    source_lines = [title, ""] + markdown.splitlines()
    lines = []
    for source_line in source_lines:
        encoded = source_line.encode("latin-1", "replace").decode("latin-1")
        # Preserve every character by wrapping instead of truncating long source lines.
        lines.extend(encoded[index : index + 100] for index in range(0, len(encoded), 100))
        if not encoded:
            lines.append("")
    pages = [lines[index : index + 54] for index in range(0, len(lines), 54)] or [[title]]
    page_refs = [4 + index * 2 for index in range(len(pages))]
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f'<< /Type /Pages /Count {len(pages)} /Kids '
            f'[{" ".join(f"{number} 0 R" for number in page_refs)}] >>'
        ).encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    }
    for index, page_lines in enumerate(pages):
        page_number = 4 + index * 2
        content_number = page_number + 1
        commands = ["BT /F1 8 Tf 36 806 Td 10 TL"]
        commands.extend(f"({_pdf_escape(line)}) Tj T*" for line in page_lines)
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        objects[page_number] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_number} 0 R >>"
        ).encode("ascii")
        objects[content_number] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = {0: 0}
    for number in range(1, max(objects) + 1):
        offsets[number] = len(output)
        output.extend(f"{number} 0 obj\n".encode("ascii"))
        output.extend(objects[number])
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {max(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for number in range(1, max(objects) + 1):
        output.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {max(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(output))
