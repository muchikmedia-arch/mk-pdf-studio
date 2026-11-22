"""Tablas de un PDF (digital o escaneado) a Excel, con números que se pueden sumar."""
import re

import pymupdf
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import scanlayout
from .common import NULL_PROGRESS, UserError, open_pdf, page_kind

_NUM_RE = re.compile(r"^\(?-?\s*(S/\.?|US\$|\$|€)?\s*-?\s*[\d.,\s]+\)?\s*%?$")


def parse_number(text):
    """'3,500.00' -> (3500.0, formato). Devuelve (None, None) si no es número."""
    if text is None:
        return None, None
    t = str(text).strip()
    if not t or len(t) > 30 or not _NUM_RE.match(t) or not re.search(r"\d", t):
        return None, None
    negative = t.startswith("(") and t.endswith(")") or "-" in t.replace("S/", "")[:3]
    currency = None
    m = re.search(r"S/\.?|US\$|\$|€", t)
    if m:
        currency = m.group(0)
    percent = t.endswith("%")
    core = re.sub(r"[^\d.,]", "", t)
    if not core:
        return None, None
    # Decidir separador decimal
    if "," in core and "." in core:
        if core.rfind(",") > core.rfind("."):
            core = core.replace(".", "").replace(",", ".")    # 1.234,56
        else:
            core = core.replace(",", "")                       # 1,234.56
    elif "," in core:
        parts = core.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            core = core.replace(",", ".")                      # 12,5 -> decimal
        elif all(len(p) == 3 for p in parts[1:]):
            core = core.replace(",", "")                       # 1,234,567
        else:
            return None, None
    elif "." in core:
        parts = core.split(".")
        if len(parts) > 2 and all(len(p) == 3 for p in parts[1:]):
            core = core.replace(".", "")                       # 1.234.567
    # números como códigos con ceros a la izquierda (DNI, RUC, códigos) se dejan como texto
    digits = re.sub(r"\D", "", core)
    if len(digits) >= 8 and "." not in core:
        return None, None
    if core.startswith("0") and len(core) > 1 and not core.startswith("0."):
        return None, None
    try:
        value = float(core)
    except ValueError:
        return None, None
    if negative:
        value = -value
    decimals = len(core.split(".")[1]) if "." in core else 0
    if percent:
        return value / 100.0, "0.00%" if decimals else "0%"
    fmt = "#,##0" + ("." + "0" * min(decimals, 4) if decimals else "")
    if currency:
        prefix = '"S/ "' if currency.startswith("S/") else f'"{currency} "'
        fmt = prefix + fmt
    return (int(value) if decimals == 0 and value.is_integer() else value), fmt


def _clean_cell(v):
    if v is None:
        return None
    v = re.sub(r"[ \t]+", " ", str(v)).strip()
    v = re.sub(r"\s*\n\s*", "\n", v)
    v = re.sub(r"^N\s*°\s*\n?\s*\.$", "N.°", v)
    return v or None


def _extract(page, tab):
    """Texto de cada celda: palabras cuyo centro cae dentro de la celda (sin invadir vecinas)."""
    words = page.get_text("words", sort=True)
    data = []
    try:
        for row in tab.rows:
            out = []
            for cell in row.cells:
                if cell is None:
                    out.append(None)
                    continue
                x0, y0, x1, y1 = cell
                inside = [w for w in words if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
                lines, last_key, last_y = [], None, None
                for w in inside:
                    key = (w[5], w[6])
                    yc = (w[1] + w[3]) / 2
                    if lines and (key == last_key or (last_y is not None and abs(yc - last_y) < 2.5)):
                        lines[-1].append(w[4])
                    else:
                        lines.append([w[4]])
                    last_key, last_y = key, yc
                out.append("\n".join(" ".join(l) for l in lines))
            data.append(out)
    except Exception:
        data = tab.extract()
    return [r for r in data if any((c or "").strip() for c in r)]


def _tables_on_page(page, borderless):
    found = []
    try:
        tabs = page.find_tables()
        found = [t for t in tabs.tables if t.row_count >= 2 and t.col_count >= 2]
    except Exception:
        found = []
    if not found and borderless:
        try:
            tabs = page.find_tables(strategy="text", min_words_vertical=3, min_words_horizontal=2)
            found = [t for t in tabs.tables if t.row_count >= 3 and t.col_count >= 2]
        except Exception:
            found = []
    return found


def pdf_to_excel(src: str, dst: str, pages=None, borderless: bool = True, one_sheet: bool = False,
                 progress=NULL_PROGRESS) -> dict:
    doc = open_pdf(src)
    idx = pages if pages else list(range(len(doc)))
    work = pymupdf.open()
    n = len(idx)
    progress(0.02, "Revisando el documento…")
    page_map = []
    analyzed = {}
    for k, i in enumerate(idx):
        if page_kind(doc[i]) == "escaneada":
            progress(0.05 + 0.7 * k / n, f"Reconociendo texto (OCR): página {k + 1} de {n}")
            analyzed[i] = scanlayout.analyze_page(doc[i], progress=progress.sub(0.05 + 0.7 * k / n,
                                                                                0.05 + 0.7 * (k + 1) / n))
    scanlayout.fix_roman_headings([analyzed[i] for i in idx if i in analyzed])
    for i in idx:
        if i in analyzed:
            scanlayout.build_page(work, analyzed[i])
        else:
            work.insert_pdf(doc, from_page=i, to_page=i)
        page_map.append(i)

    wb = Workbook()
    wb.remove(wb.active)
    thin = Side(style="thin", color="808080")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="E8EEF7")
    total_tables = 0
    sheet = None
    next_row = 1

    for k, page in enumerate(work):
        progress(0.78 + 0.2 * k / max(n, 1), f"Buscando tablas: página {k + 1} de {n}")
        for t_index, tab in enumerate(_tables_on_page(page, borderless)):
            data = _extract(page, tab)
            if not data:
                continue
            total_tables += 1
            if one_sheet:
                if sheet is None:
                    sheet = wb.create_sheet("Tablas")
                ws = sheet
                ws.cell(row=next_row, column=1, value=f"Página {page_map[k] + 1} - Tabla {t_index + 1}").font = Font(bold=True, color="1F4E79")
                start = next_row + 1
            else:
                ws = wb.create_sheet(f"Pág {page_map[k] + 1} - Tabla {t_index + 1}"[:31])
                start = 1
            ncols = max(len(r) for r in data)
            # anchos de columna según la tabla del PDF
            try:
                cols_x = [c for c in tab.cells if c]
                xs = sorted({round(c[0], 1) for c in cols_x} | {round(c[2], 1) for c in cols_x})
            except Exception:
                xs = []
            header_rows = 1
            for r_i, row in enumerate(data):
                excel_row = start + r_i
                c_i = 0
                while c_i < ncols:
                    val = _clean_cell(row[c_i] if c_i < len(row) else None)
                    cell = ws.cell(row=excel_row, column=c_i + 1)
                    number, fmt = parse_number(val) if r_i >= header_rows else (None, None)
                    if number is not None:
                        cell.value = number
                        cell.number_format = fmt
                        cell.alignment = Alignment(horizontal="right", vertical="top")
                    else:
                        cell.value = val
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                    cell.border = border
                    if r_i < header_rows:
                        cell.font = Font(bold=True)
                        cell.fill = header_fill
                        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
                    # celdas combinadas (None a la derecha de un valor)
                    span = 1
                    while c_i + span < ncols and c_i + span < len(row) and row[c_i + span] is None and val is not None:
                        ws.cell(row=excel_row, column=c_i + span + 1).border = border
                        span += 1
                    if span > 1:
                        ws.merge_cells(start_row=excel_row, start_column=c_i + 1, end_row=excel_row, end_column=c_i + span)
                    c_i += span
            for c in range(ncols):
                letter = get_column_letter(c + 1)
                longest = max((len(str(r[c] or "").split("\n")[0]) for r in data if c < len(r)), default=8)
                width = min(60, max(8, longest * 1.1 + 2))
                current = ws.column_dimensions[letter].width or 0
                ws.column_dimensions[letter].width = max(current, width)
            next_row = start + len(data) + 2
    work.close()
    doc.close()

    if total_tables == 0:
        raise UserError("No se encontraron tablas en el documento. Si las tablas no tienen líneas, "
                        "activa «Buscar también tablas sin bordes».")
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = True
        ws.freeze_panes = None
    wb.save(dst)
    progress(1.0, "Listo")
    return {"tables": total_tables, "pages": n}
