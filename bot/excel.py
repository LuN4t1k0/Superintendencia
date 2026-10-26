from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
import re

from openpyxl import load_workbook
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def read_ruts(file_bytes: bytes) -> tuple[Workbook, Worksheet, int, list[int]]:
    """Load workbook and return workbook, active sheet, RUT column, and data rows."""
    wb = load_workbook(BytesIO(file_bytes))
    ws = wb.active

    rut_col = None
    for cell in next(ws.iter_rows(1, 1)):
        if cell.value and "rut" in str(cell.value).lower():
            rut_col = cell.column
            break

    if rut_col is None:
        raise ValueError("No se encontró columna con 'RUT' en el header")

    data_rows = [
        row
        for row in range(2, ws.max_row + 1)
        if ws.cell(row, rut_col).value is not None
    ]
    return wb, ws, rut_col, data_rows


def find_or_create_afp2_column(ws: Worksheet) -> int:
    """Return the 1-based AFP 2 column index, creating it when absent."""
    for cell in next(ws.iter_rows(1, 1)):
        if cell.value and str(cell.value).strip().upper() == "AFP 2":
            return cell.column

    new_col = ws.max_column + 1
    ws.cell(1, new_col, "AFP 2")
    return new_col


def get_pending_rows(
    ws: Worksheet, rut_col: int, afp2_col: int, data_rows: list[int]
) -> list[int]:
    """Return rows where AFP 2 is still empty (not yet processed)."""
    return [row for row in data_rows if not ws.cell(row, afp2_col).value]


def write_afp(ws: Worksheet, row: int, col: int, value: str) -> None:
    ws.cell(row, col, value)


def to_bytes(wb: Workbook) -> bytes:
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_afp2_zip_bytes(wb: Workbook) -> bytes:
    """Return one XLSX per AFP 2 value, packaged in a ZIP archive.

    The active worksheet is partitioned dynamically using the values present
    in the ``AFP 2`` column. Headers, workbook formatting and other worksheets
    are preserved in every generated workbook.
    """
    source = to_bytes(wb)
    source_wb = load_workbook(BytesIO(source))
    source_ws = source_wb.active
    afp2_col = find_or_create_afp2_column(source_ws)
    groups: dict[str, list[int]] = {}
    for row in range(2, source_ws.max_row + 1):
        if source_ws.cell(row, 1).value is None and all(
            source_ws.cell(row, col).value is None for col in range(1, source_ws.max_column + 1)
        ):
            continue
        raw_value = source_ws.cell(row, afp2_col).value
        key = str(raw_value).strip().upper() if raw_value is not None else ""
        groups.setdefault(key or "SIN_AFP2", []).append(row)

    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as output_zip:
        for key, rows in sorted(groups.items()):
            group_wb = load_workbook(BytesIO(source))
            group_ws = group_wb.active
            keep = set(rows)
            for row in range(group_ws.max_row, 1, -1):
                if row not in keep:
                    group_ws.delete_rows(row, 1)
            filename = f"AFP2_{_safe_filename(key)}.xlsx"
            output_zip.writestr(filename, to_bytes(group_wb))
    return archive.getvalue()


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Z0-9_-]+", "_", value).strip("_") or "SIN_AFP2"
