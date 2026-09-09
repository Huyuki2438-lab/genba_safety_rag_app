from __future__ import annotations

import base64
import io
import re
from datetime import datetime
from typing import Iterable


SECTION_TITLES = {
    "OVERALL": "1. 総合評価",
    "SUMMARY": "2. リスク概要",
    "RISKS": "3. 想定される危険",
    "SOLUTIONS": "4. 安全対策",
    "ADDITIONAL": "5. 追加情報",
}
SECTION_MARKER = re.compile(r"^\s*\[SECTION:([^\]]+)\]\s*$", re.IGNORECASE)
MARKDOWN_PREFIX = re.compile(r"^\s{0,3}(?:#{1,6}\s*|[-*+]\s+|\d+[.)]\s+|>\s?)")
MARKDOWN_EMPHASIS = re.compile(r"(\*\*|__|`|~~)")


def _plain_text(value: str) -> str:
    """Keep report content readable in cells while removing Markdown controls."""
    text = MARKDOWN_PREFIX.sub("", value).strip()
    text = MARKDOWN_EMPHASIS.sub("", text)
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)


def _summary_line_breaks(value: str) -> str | None:
    """Render Markdown risk-table columns as line breaks in the Excel cell."""
    if not (value.startswith("|") and value.endswith("|")):
        return value

    fields = [field.strip() for field in value[1:-1].split("|")]
    if fields and all(re.fullmatch(r":?-{3,}:?", field) for field in fields):
        return None
    return "\n".join(field for field in fields if field)


def _report_sections(markdown: str) -> Iterable[tuple[str, list[str]]]:
    sections: dict[str, list[str]] = {key: [] for key in SECTION_TITLES}
    active = "OVERALL"
    saw_marker = False
    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        marker = SECTION_MARKER.match(raw_line)
        if marker:
            key = marker.group(1).upper()
            if key in sections:
                active = key
                saw_marker = True
            continue
        cleaned = _plain_text(raw_line)
        if active == "SUMMARY" and cleaned:
            cleaned = _summary_line_breaks(cleaned)
        if cleaned:
            sections[active].append(cleaned)

    if not saw_marker:
        sections["OVERALL"] = [_plain_text(line) for line in markdown.splitlines() if _plain_text(line)]

    for key, title in SECTION_TITLES.items():
        yield title, sections[key] or ["情報はありません。"]


def _image_from_data_url(data_url: str):
    from openpyxl.drawing.image import Image

    header, separator, encoded = data_url.partition(",")
    if not separator or not header.lower().startswith("data:image/"):
        return None
    try:
        binary = base64.b64decode(encoded, validate=True)
        image = Image(io.BytesIO(binary))
    except Exception:
        return None
    scale = min(1, 600 / image.width, 360 / image.height)
    image.width = int(image.width * scale)
    image.height = int(image.height * scale)
    return image


def generate_excel_report(context: dict[str, object]) -> bytes:
    """Create an A4-printable workbook mirroring the PDF report's sections."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "安全分析レポート"
    sheet.sheet_view.showGridLines = False
    sheet.page_setup.orientation = "portrait"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A4
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_margins.left = 0.35
    sheet.page_margins.right = 0.35
    sheet.page_margins.top = 0.4
    sheet.page_margins.bottom = 0.4
    sheet.freeze_panes = "A5"
    for column, width in enumerate((15, 15, 15, 15, 15, 15, 15, 15), start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width

    navy = "17365D"
    blue = "D9EAF7"
    pale_blue = "EAF3F8"
    white = "FFFFFF"
    dark = "1F2937"
    gray = "F3F4F6"
    thin = Side(style="thin", color="AAB7C4")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    centered = Alignment(horizontal="center", vertical="center", wrap_text=True)
    wrapped = Alignment(vertical="top", wrap_text=True)

    title = str(context.get("title") or "現場安全 危険分析レポート")
    sheet.merge_cells("A1:H2")
    cell = sheet["A1"]
    cell.value = title
    cell.font = Font(name="Meiryo", size=18, bold=True, color=white)
    cell.fill = PatternFill("solid", fgColor=navy)
    cell.alignment = centered
    sheet.row_dimensions[1].height = 25
    sheet.row_dimensions[2].height = 25

    sheet.merge_cells("A3:H3")
    cell = sheet["A3"]
    cell.value = f"出力日時: {context.get('generated_at') or datetime.now().strftime('%Y/%m/%d %H:%M')}"
    cell.font = Font(name="Meiryo", size=10, color=dark)
    cell.fill = PatternFill("solid", fgColor=gray)
    cell.alignment = Alignment(horizontal="right", vertical="center")
    sheet.row_dimensions[3].height = 20

    details = (
        ("現場名", str(context.get("site_name") or "－")),
        ("作業内容", str(context.get("work_content") or "－")),
        ("主な危険", str(context.get("main_risk") or "－")),
        ("登録者", str(context.get("created_by") or "－")),
    )
    for row, (label, value) in enumerate(details, start=5):
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
        sheet.merge_cells(start_row=row, start_column=3, end_row=row, end_column=8)
        label_cell = sheet.cell(row, 1, label)
        label_cell.font = Font(name="Meiryo", size=10, bold=True, color=dark)
        label_cell.fill = PatternFill("solid", fgColor=blue)
        label_cell.alignment = centered
        label_cell.border = border
        value_cell = sheet.cell(row, 3, value)
        value_cell.font = Font(name="Meiryo", size=10, color=dark)
        value_cell.alignment = wrapped
        value_cell.border = border
        for column in range(1, 9):
            sheet.cell(row, column).border = border
        sheet.row_dimensions[row].height = 24

    next_row = 10
    image = _image_from_data_url(str(context.get("image_data_url") or ""))
    if image:
        sheet.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=8)
        image_title = sheet.cell(next_row, 1, "分析対象画像")
        image_title.font = Font(name="Meiryo", size=11, bold=True, color=white)
        image_title.fill = PatternFill("solid", fgColor=navy)
        image_title.alignment = centered
        next_row += 1
        sheet.add_image(image, f"A{next_row}")
        image_rows = max(14, int(image.height / 19) + 2)
        for row in range(next_row, next_row + image_rows):
            sheet.row_dimensions[row].height = 19
        next_row += image_rows + 1

    markdown = str(context.get("markdown") or "")
    for section_title, lines in _report_sections(markdown):
        sheet.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=8)
        header = sheet.cell(next_row, 1, section_title)
        header.font = Font(name="Meiryo", size=12, bold=True, color=white)
        header.fill = PatternFill("solid", fgColor=navy)
        header.alignment = Alignment(vertical="center")
        sheet.row_dimensions[next_row].height = 24
        next_row += 1
        for line in lines:
            sheet.merge_cells(start_row=next_row, start_column=1, end_row=next_row, end_column=8)
            body = sheet.cell(next_row, 1, line)
            body.font = Font(name="Meiryo", size=10, color=dark)
            body.fill = PatternFill("solid", fgColor=pale_blue)
            body.alignment = wrapped
            for column in range(1, 9):
                sheet.cell(next_row, column).border = border
            # 15 pt per visual line keeps wrapped Japanese text legible in print.
            visual_lines = sum(max(1, len(part) // 72 + 1) for part in line.splitlines())
            sheet.row_dimensions[next_row].height = max(22, min(150, 15 * visual_lines))
            next_row += 1
        next_row += 1

    sheet.print_title_rows = "1:3"
    sheet.print_area = f"A1:H{max(next_row - 1, 1)}"
    sheet.oddFooter.center.text = "安全分析レポート  Page &P / &N"
    sheet.oddFooter.center.size = 8
    workbook.properties.creator = "現場安全分析アプリ"
    workbook.properties.title = title
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
