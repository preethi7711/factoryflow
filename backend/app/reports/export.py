"""Render a Report envelope as CSV or XLSX. Same columns, labels and totals as the JSON."""

import csv
import io

from openpyxl import Workbook

from app.reports.schemas import Report

CSV_MEDIA = "text/csv"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _cell(value: object) -> object:
    return "" if value is None else value


def _totals_row(report: Report) -> list[object] | None:
    if not report.totals:
        return None
    row: list[object] = []
    for i, col in enumerate(report.columns):
        if i == 0:
            row.append("TOTAL")
        else:
            row.append(report.totals.get(col.key, ""))
    return row


def to_csv(report: Report) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([col.label for col in report.columns])
    for row in report.rows:
        writer.writerow([_cell(row.get(col.key)) for col in report.columns])
    totals = _totals_row(report)
    if totals is not None:
        writer.writerow(totals)
    # utf-8-sig so Excel opens the rupee sign and other non-ASCII correctly.
    return buffer.getvalue().encode("utf-8-sig")


def to_xlsx(report: Report) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = report.name[:31]  # Excel caps sheet names at 31 chars
    sheet.append([col.label for col in report.columns])
    for row in report.rows:
        sheet.append([_cell(row.get(col.key)) for col in report.columns])
    totals = _totals_row(report)
    if totals is not None:
        sheet.append(totals)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
