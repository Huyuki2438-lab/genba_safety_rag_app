from __future__ import annotations

import io
from copy import copy
from datetime import timezone, timedelta
from decimal import Decimal

from backend.app.schemas.usage import (
    UsageBreakdown,
    UsagePricingSettingsResponse,
    UsageQueryResponse,
)
from backend.app.services.excel_service import _sanitize_excel_text


JST = timezone(timedelta(hours=9), name="Asia/Tokyo")


def _number(value: Decimal | int | None) -> float | int | None:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _text(value: object | None) -> str:
    return _sanitize_excel_text("" if value is None else str(value))


def generate_usage_excel(
    result: UsageQueryResponse,
    pricing: UsagePricingSettingsResponse,
    *,
    construction_name: str | None = None,
    model: str | None = None,
    analysis_state: str | None = None,
) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = {
        name: workbook.create_sheet(name)
        for name in ("概要", "解析別明細", "月別集計", "工事別集計", "モデル別集計")
    }
    navy = "1F4E78"
    pale = "F3F6F9"
    border = Border(bottom=Side(style="thin", color="CBD5E1"))

    def title(sheet, value: str, end_column: int) -> None:
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=end_column)
        cell = sheet.cell(1, 1, value)
        cell.font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=navy)
        cell.alignment = Alignment(vertical="center")
        sheet.row_dimensions[1].height = 26
        sheet.sheet_view.showGridLines = False

    def header(sheet, row: int, labels: list[str]) -> None:
        for column, label in enumerate(labels, 1):
            cell = sheet.cell(row, column, label)
            cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor=navy)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        sheet.row_dimensions[row].height = 28

    overview = sheets["概要"]
    title(overview, "利用料金概要", 4)
    overview_rows = [
        ("対象期間", f"{result.date_from.isoformat()} ～ {result.date_to.isoformat()}"),
        ("工事名", construction_name or "すべて"),
        ("モデル", model or "すべて"),
        ("解析状態", {"success": "成功", "failure": "失敗"}.get(analysis_state or "", "すべて")),
    ]
    for row, (label, value) in enumerate(overview_rows, 3):
        overview.cell(row, 1, label).font = Font(name="Arial", bold=True)
        overview.cell(row, 2, _text(value))

    overview.cell(8, 1, "保存済み為替レート").font = Font(name="Arial", bold=True, color=navy)
    rate_row = 9
    for item in sorted(pricing.exchange_rates, key=lambda value: value.exchange_rate_effective_date):
        overview.cell(rate_row, 1, item.exchange_rate_effective_date)
        overview.cell(rate_row, 1).number_format = "yyyy-mm-dd"
        overview.cell(rate_row, 2, _number(item.jpy_per_usd))
        overview.cell(rate_row, 2).number_format = '0.######## "JPY/USD"'
        overview.cell(rate_row, 3, _text(item.source))
        rate_row += 1
    if rate_row == 9:
        overview.cell(rate_row, 1, "未設定")

    summary_row = max(rate_row + 2, 12)
    header(overview, summary_row, ["集計項目", "値", "備考"])
    summary = result.summary
    summary_values = [
        ("API呼出し数", summary.call_count, ""),
        ("成功数", summary.success_count, ""),
        ("失敗数", summary.failure_count, ""),
        ("推定料金（USD）", summary.estimated_cost_usd_total, "未確定がある場合は空欄"),
        ("計算可能分（USD）", summary.estimated_cost_usd_subtotal, ""),
        ("推定料金（JPY）", summary.estimated_cost_jpy_total, "未確定がある場合は空欄"),
        ("計算可能分（JPY）", summary.estimated_cost_jpy_subtotal, ""),
        ("料金未確定件数", summary.jpy_unavailable_count, ""),
        ("合計トークン", summary.total_tokens.known_total, f"未取得 {summary.total_tokens.unknown_count}件"),
    ]
    for row, (label, value, note) in enumerate(summary_values, summary_row + 1):
        overview.cell(row, 1, label)
        overview.cell(row, 2, _number(value))
        overview.cell(row, 3, note)
        overview.cell(row, 2).number_format = (
            "0.000000" if "USD" in label else "#,##0.00" if "JPY" in label else "#,##0"
        )
        if row % 2 == 0:
            for column in range(1, 4):
                overview.cell(row, column).fill = PatternFill("solid", fgColor=pale)
    overview.column_dimensions["A"].width = 29
    overview.column_dimensions["B"].width = 24
    overview.column_dimensions["C"].width = 42
    overview.freeze_panes = f"A{summary_row + 1}"

    detail = sheets["解析別明細"]
    detail_headers = [
        "解析日時", "工事名", "モデル名", "解析状態", "入力トークン",
        "出力トークン", "思考トークン", "キャッシュトークン", "合計トークン",
        "推定料金（USD）", "推定料金（JPY）", "適用為替レート（JPY/USD）",
        "為替適用日", "料金計算状態", "未確定理由", "usage_id",
    ]
    title(detail, "解析別料金明細", len(detail_headers))
    header(detail, 3, detail_headers)
    for row_index, item in enumerate(result.details, 4):
        created = item.created_at.astimezone(JST).replace(tzinfo=None)
        values = [
            created, _text(item.construction_name), _text(item.model),
            "成功" if item.analysis_status == "success" else "失敗",
            item.prompt_token_count, item.candidates_token_count, item.thoughts_token_count,
            item.cached_content_token_count, item.total_token_count,
            _number(item.estimated_cost_usd), _number(item.estimated_cost_jpy),
            _number(item.exchange_rate_jpy_per_usd), item.exchange_rate_effective_date,
            {"estimated": "推定済み", "partial": "一部未確定", "unavailable": "未確定"}[item.pricing_status],
            _text(item.pricing_error_reason), item.usage_id,
        ]
        for column, value in enumerate(values, 1):
            detail.cell(row_index, column, value)
    detail.freeze_panes = "A4"
    detail.auto_filter.ref = f"A3:{get_column_letter(len(detail_headers))}{max(3, len(result.details) + 3)}"
    detail.column_dimensions["A"].width = 19
    detail.column_dimensions["B"].width = 24
    detail.column_dimensions["C"].width = 25
    for column in range(4, 17):
        detail.column_dimensions[get_column_letter(column)].width = 18
    detail.column_dimensions["O"].width = 38
    detail.column_dimensions["P"].width = 38
    for cell in detail[3]:
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in range(4, len(result.details) + 4):
        detail.cell(row, 1).number_format = "yyyy-mm-dd hh:mm"
        for column in range(5, 10):
            detail.cell(row, column).number_format = "#,##0"
        detail.cell(row, 10).number_format = "0.000000"
        detail.cell(row, 11).number_format = "#,##0.00"
        detail.cell(row, 12).number_format = "0.########"
        detail.cell(row, 13).number_format = "yyyy-mm-dd"

    def breakdown_sheet(sheet_name: str, title_text: str, rows: list[UsageBreakdown]) -> None:
        sheet = sheets[sheet_name]
        labels = [
            "区分", "API呼出し", "成功", "失敗", "推定料金（USD）",
            "計算可能分（USD）", "推定料金（JPY）", "計算可能分（JPY）",
            "料金未確定件数", "合計トークン",
        ]
        title(sheet, title_text, len(labels))
        header(sheet, 3, labels)
        for row_index, item in enumerate(rows, 4):
            values = [
                _text(item.label), item.call_count, item.success_count, item.failure_count,
                _number(item.estimated_cost_usd_total), _number(item.estimated_cost_usd_subtotal),
                _number(item.estimated_cost_jpy_total), _number(item.estimated_cost_jpy_subtotal),
                item.jpy_unavailable_count, item.total_tokens.known_total,
            ]
            for column, value in enumerate(values, 1):
                sheet.cell(row_index, column, value)
        sheet.freeze_panes = "A4"
        sheet.auto_filter.ref = f"A3:J{max(3, len(rows) + 3)}"
        sheet.column_dimensions["A"].width = 28
        for column in range(2, 11):
            sheet.column_dimensions[get_column_letter(column)].width = 21
        for row in range(4, len(rows) + 4):
            for column in (2, 3, 4, 9, 10):
                sheet.cell(row, column).number_format = "#,##0"
            for column in (5, 6):
                sheet.cell(row, column).number_format = "0.000000"
            for column in (7, 8):
                sheet.cell(row, column).number_format = "#,##0.00"

    breakdown_sheet("月別集計", "月別料金集計", result.monthly)
    breakdown_sheet("工事別集計", "工事別料金集計", result.by_construction)
    breakdown_sheet("モデル別集計", "モデル別料金集計", result.by_model)

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                font = copy(cell.font)
                font.name = "Arial"
                if font.sz is None:
                    font.sz = 10
                cell.font = font
                alignment = copy(cell.alignment)
                alignment.vertical = "center"
                cell.alignment = alignment
                if cell.row > 3:
                    cell.border = border
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.page_margins.left = 0.3
        sheet.page_margins.right = 0.3

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
