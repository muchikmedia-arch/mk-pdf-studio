"""Reconstrucción de páginas escaneadas.

A partir del OCR se crea una página PDF "limpia" que tiene el texto real en la misma
posición que el escaneo (márgenes, sangrías, centrado, justificado), las líneas de
las tablas como vectores y los logos/sellos/firmas como imágenes. Esa página luego
se convierte a Word con el mismo motor que los PDF digitales.
"""
import os
import re
import sys
from statistics import median

import cv2
import numpy as np
import pymupdf

from . import ocr
from .common import NULL_PROGRESS

# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------

_WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_LINUX_FONTS = "/usr/share/fonts/truetype"

FONT_FILES = {
    "Arial": (
        [os.path.join(_WIN_FONTS, "arial.ttf"), f"{_LINUX_FONTS}/liberation/LiberationSans-Regular.ttf",
         f"{_LINUX_FONTS}/liberation2/LiberationSans-Regular.ttf"],
        [os.path.join(_WIN_FONTS, "arialbd.ttf"), f"{_LINUX_FONTS}/liberation/LiberationSans-Bold.ttf",
         f"{_LINUX_FONTS}/liberation2/LiberationSans-Bold.ttf"],
    ),
    "Times New Roman": (
        [os.path.join(_WIN_FONTS, "times.ttf"), f"{_LINUX_FONTS}/liberation/LiberationSerif-Regular.ttf"],
        [os.path.join(_WIN_FONTS, "timesbd.ttf"), f"{_LINUX_FONTS}/liberation/LiberationSerif-Bold.ttf"],
    ),
    "Calibri": (
        [os.path.join(_WIN_FONTS, "calibri.ttf"), f"{_LINUX_FONTS}/crosextra/Carlito-Regular.ttf"],
        [os.path.join(_WIN_FONTS, "calibrib.ttf"), f"{_LINUX_FONTS}/crosextra/Carlito-Bold.ttf"],
    ),
}

_BASE14 = {"Arial": ("helv", "hebo"), "Times New Roman": ("tiro", "tibo"), "Calibri": ("helv", "hebo")}
_font_cache = {}


def get_fonts(family: str):
    """(fuente normal, fuente negrita) como objetos pymupdf.Font."""
    family = family if family in FONT_FILES else "Arial"
    if family in _font_cache:
        return _font_cache[family]
    reg_paths, bold_paths = FONT_FILES[family]

    def first(paths, base):
        for p in paths:
            if p and os.path.isfile(p):
                try:
                    return pymupdf.Font(fontfile=p)
                except Exception:
                    pass
        return pymupdf.Font(base)

    b14 = _BASE14[family]
    fonts = (first(reg_paths, b14[0]), first(bold_paths, b14[1]))
    _font_cache[family] = fonts
    return fonts


# ---------------------------------------------------------------------------
# Análisis de la imagen
# ---------------------------------------------------------------------------

def detect_rules(bw: np.ndarray):
    """Detecta líneas horizontales y verticales largas (bordes de tablas, rayas).

    Devuelve (segmentos_h, segmentos_v, mascara) en píxeles. Cada segmento: (x0, y0, x1, y1, grosor).
    """
    h, w = bw.shape
    hk = max(40, w // 22)
    vk = max(40, h // 45)
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 1)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk)))
    # unir pequeños cortes
    horiz = cv2.dilate(horiz, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1)))
    vert = cv2.dilate(vert, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 9)))
    hsegs, vsegs = [], []
    for c in cv2.findContours(horiz, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, ww, hh = cv2.boundingRect(c)
        if hh <= max(14, h // 250) and ww >= hk:
            hsegs.append((x + 4, y + hh / 2, x + ww - 4, y + hh / 2, max(1.0, hh - 8)))
    for c in cv2.findContours(vert, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, ww, hh = cv2.boundingRect(c)
        if ww <= max(14, w // 250) and hh >= vk:
            vsegs.append((x + ww / 2, y + 4, x + ww / 2, y + hh - 4, max(1.0, ww - 8)))
    # máscara solo con las líneas finas aceptadas (no borrar logos ni manchas grandes)
    mask = np.zeros_like(bw)
    for x0, y, x1, _, t in hsegs:
        cv2.line(mask, (int(x0) - 4, int(round(y))), (int(x1) + 4, int(round(y))), 255, int(t) + 8)
    for x, y0, _, y1, t in vsegs:
        cv2.line(mask, (int(round(x)), int(y0) - 4), (int(round(x)), int(y1) + 4), 255, int(t) + 8)
    mask = cv2.bitwise_and(mask, cv2.dilate(cv2.bitwise_or(horiz, vert), cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))))
    return hsegs, vsegs, mask


def find_graphics(bw: np.ndarray, char_h: float):
    """Regiones que no son texto: logos, fotos, sellos, firmas (en píxeles)."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, connectivity=8)
    big = np.zeros_like(bw)
    for i in range(1, n):
        x, y, ww, hh, area = stats[i]
        if area < 30:
            continue
        if hh > 2.6 * char_h or (ww > 6 * char_h and hh > 1.6 * char_h and area > 0.25 * ww * hh):
            big[labels == i] = 255
    if not big.any():
        return []
    k = int(max(5, char_h * 1.2))
    grouped = cv2.dilate(big, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    # añadir componentes pequeños cercanos (partes del logo o la firma)
    regions = []
    for c in cv2.findContours(grouped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, ww, hh = cv2.boundingRect(c)
        if ww * hh >= (char_h * 3.5) ** 2:
            regions.append([x, y, x + ww, y + hh])
    return regions


_ASC = set("bdfhklt") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()[]{}/\\|!?¿¡%&$#@'\"“”")
_ACC_LOW = set("áéíóúüñi")
_ACC_CAP = set("ÁÉÍÓÚÜÑ")
_DESC = set("gjpqyQ()[]{},;|_")


def word_metrics(word: str, ink_h: float):
    """Tamaño de letra (em) estimado a partir de la altura de tinta de la palabra."""
    chars = set(word)
    if chars & _ACC_CAP:
        top = 0.90
    elif chars & _ASC:
        top = 0.72
    elif chars & _ACC_LOW:
        top = 0.74 if chars & set("áéíóúüñ") else 0.71
    elif re.search(r"[a-zçß]", word):
        top = 0.52
    else:
        return None  # solo puntuación
    if chars & set("gjpqyQ()[]{}|_"):
        bottom = 0.21
    elif chars & set(",;"):
        bottom = 0.15
    else:
        bottom = 0.0
    if chars <= set(",;.:-–_"):
        return None
    return ink_h / (top + bottom)


def ink_box(bw: np.ndarray, x0, y0, x1, y1):
    h, w = bw.shape
    x0, y0 = max(0, int(x0) - 1), max(0, int(y0) - 2)
    x1, y1 = min(w, int(x1) + 1), min(h, int(y1) + 2)
    if x1 <= x0 or y1 <= y0:
        return None
    crop = bw[y0:y1, x0:x1]
    rows = np.where(crop.max(axis=1) > 0)[0]
    cols = np.where(crop.max(axis=0) > 0)[0]
    if len(rows) == 0:
        return None
    return (x0 + cols[0], y0 + rows[0], x0 + cols[-1] + 1, y0 + rows[-1] + 1, crop)


def stroke_ratio(crop: np.ndarray, em_px: float):
    area = float(np.count_nonzero(crop))
    if area < 20 or em_px <= 0:
        return None
    contours = cv2.findContours(crop, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0]
    perim = sum(cv2.arcLength(c, True) for c in contours)
    if perim <= 0:
        return None
    return (2.0 * area / perim) / em_px


STANDARD_SIZES = [7, 8, 9, 10, 10.5, 11, 11.5, 12, 13, 14, 16, 18, 20, 22, 24, 26, 28, 32, 36, 40, 48]


def snap_size(s, body, short=False):
    tol = 0.13 if short else 0.07
    if body and abs(s - body) <= max(0.7, tol * body):
        return body
    nearest = min(STANDARD_SIZES, key=lambda v: abs(v - s))
    if abs(nearest - s) <= 0.09 * s:
        return float(nearest)
    return round(s * 2) / 2


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

class ScannedPage:
    """Resultado del análisis de una página escaneada (coordenadas en puntos)."""

    def __init__(self):
        self.width = self.height = 0
        self.lines = []      # dict: words, x0, x1, top, base, size, bold, align, text
        self.hrules = []     # (x0, y, x1, grosor)
        self.vrules = []     # (x, y0, y1, grosor)
        self.images = []     # (rect, png_bytes)
        self.angle = 0.0
        self.quarter = 0
        self.plain_text = ""


def analyze_page(page: pymupdf.Page, dpi: int = None, fix_orientation: bool = True,
                 progress=NULL_PROGRESS) -> ScannedPage:
    dpi = dpi or ocr.ocr_dpi()
    sp = ScannedPage()
    clean, rgb, angle, q = ocr.prepare_page_image(page, dpi, fix_orientation=False)
    progress(0.15)
    sp.angle, sp.quarter = angle, q
    px2pt = 72.0 / dpi
    hpx, wpx = clean.shape
    sp.width, sp.height = wpx * px2pt, hpx * px2pt

    bw = ocr.binarize(clean)
    hsegs, vsegs, rule_mask = detect_rules(bw)
    clean_nolines = clean.copy()
    clean_nolines[rule_mask > 0] = 255
    bw_nolines = bw.copy()
    bw_nolines[rule_mask > 0] = 0

    odoc, opage = ocr.ocr_gray(clean_nolines, dpi)
    words = ocr.ocr_words(opage)
    good, ratio = ocr.text_quality(opage.get_text())
    if fix_orientation and (len(words) < 8 or ratio < 0.45):
        q = ocr.detect_orientation(clean)
        if q:
            odoc.close()
            page_rot = ScannedPageRotated(page, q)
            return analyze_rotated(page_rot, dpi, q, progress)
    progress(0.7)

    # ---- medidas de cada palabra (en píxeles) ----
    items = []
    for wd in words:
        x0, y0, x1, y1 = [v / px2pt for v in wd["bbox"]]
        ib = ink_box(bw_nolines, x0, y0, x1, y1)
        if ib is None:
            continue
        ix0, iy0, ix1, iy1, crop = ib
        text = ocr.fix_text(wd["text"])
        em = word_metrics(text, max(1.0, (iy1 - iy0) - 0.9 * dpi / 300.0))
        items.append({"text": text, "x0": x0, "x1": x1, "top": iy0, "bot": iy1, "ix0": ix0, "ix1": ix1,
                      "em": em, "desc": bool(set(text) & _DESC), "crop": crop})

    ems = [it["em"] for it in items if it["em"]]
    char_h = median(ems) * 0.72 if ems else 30.0

    # ---- gráficos (logos, sellos, firmas) ----
    regions = find_graphics(bw_nolines, char_h)
    keep_regions = []
    page_area = float(wpx * hpx)
    for r in regions:
        if (r[2] - r[0]) * (r[3] - r[1]) > 0.55 * page_area:
            continue  # fondo o marco de una foto, no es un logo
        inside = [it for it in items if r[0] <= (it["x0"] + it["x1"]) / 2 <= r[2] and r[1] <= (it["top"] + it["bot"]) / 2 <= r[3]]
        area = (r[2] - r[0]) * (r[3] - r[1])
        covered = sum((it["x1"] - it["x0"]) * (it["bot"] - it["top"]) for it in inside
                      if ocr.text_quality(it["text"])[0])
        if inside and covered > 0.45 * area:
            continue  # es texto grande, no imagen
        keep_regions.append(r)
        for it in inside:
            it["drop"] = True
    items = [it for it in items if not it.get("drop")]

    for r in keep_regions:
        pad = 4
        x0, y0, x1, y1 = max(0, r[0] - pad), max(0, r[1] - pad), min(wpx, r[2] + pad), min(hpx, r[3] + pad)
        crop = rgb[y0:y1, x0:x1].copy()
        paper = clean[y0:y1, x0:x1] > 215
        crop[paper] = 255
        ok, png = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        if ok:
            sp.images.append((pymupdf.Rect(x0 * px2pt, y0 * px2pt, x1 * px2pt, y1 * px2pt), png.tobytes()))

    # ---- reglas a puntos ----
    for x0, y0, x1, y1, t in hsegs:
        sp.hrules.append((x0 * px2pt, y0 * px2pt, x1 * px2pt, max(0.5, t * px2pt)))
    for x0, y0, x1, y1, t in vsegs:
        sp.vrules.append((x0 * px2pt, y0 * px2pt, y1 * px2pt, max(0.5, t * px2pt)))

    # ---- agrupar palabras en renglones ----
    items.sort(key=lambda it: ((it["top"] + it["bot"]) / 2, it["x0"]))
    rows = []
    for it in items:
        cy = (it["top"] + it["bot"]) / 2
        placed = False
        for row in reversed(rows[-6:]):
            rtop, rbot = row["top"], row["bot"]
            core_top = rtop + (rbot - rtop) * 0.15
            core_bot = rbot - (rbot - rtop) * 0.15
            if core_top <= cy <= core_bot or (it["top"] < core_bot and it["bot"] > core_top and
                                              min(it["bot"], rbot) - max(it["top"], rtop) > 0.5 * min(it["bot"] - it["top"], rbot - rtop)):
                row["items"].append(it)
                row["top"] = min(rtop, it["top"])
                row["bot"] = max(rbot, it["bot"])
                placed = True
                break
        if not placed:
            rows.append({"items": [it], "top": it["top"], "bot": it["bot"]})

    vxs = [(x0, y0, y1) for (x0, y0, x1, y1, t) in vsegs]
    segments = []
    for row in rows:
        row["items"].sort(key=lambda it: it["x0"])
        row_ems = [it["em"] for it in row["items"] if it["em"]]
        em_row = median(row_ems) if row_ems else char_h / 0.72
        cur = [row["items"][0]]
        for it in row["items"][1:]:
            prev = cur[-1]
            gap = it["x0"] - prev["x1"]
            crosses_rule = any(prev["x1"] <= vx <= it["x0"] and vy0 <= row["bot"] and vy1 >= row["top"]
                               for vx, vy0, vy1 in vxs)
            if gap > max(2.2 * em_row, 40 * dpi / 300) or crosses_rule:
                segments.append(cur)
                cur = [it]
            else:
                cur.append(it)
        segments.append(cur)

    # ---- tamaño de letra y negrita por renglón ----
    seg_info = []
    for seg in segments:
        seg_ems = [it["em"] for it in seg if it["em"]]
        em = median(seg_ems) if seg_ems else char_h / 0.72
        ratios = [stroke_ratio(it["crop"], em) for it in seg]
        ratios = [r for r in ratios if r]
        sr = median(ratios) if ratios else None
        nondesc = [it["bot"] for it in seg if not it["desc"]]
        base = median(nondesc) if nondesc else median(it["bot"] for it in seg) - 0.21 * em
        nchars = sum(len(it["text"]) for it in seg)
        seg_info.append({"items": seg, "em": em, "sr": sr, "base": base, "nchars": nchars})

    # tamaño del cuerpo de texto
    weighted = {}
    for s in seg_info:
        key = round(s["em"] * px2pt * 2) / 2
        weighted[key] = weighted.get(key, 0) + s["nchars"]
    body = max(weighted, key=weighted.get) if weighted else 11.0
    near = min(STANDARD_SIZES, key=lambda v: abs(v - body))
    if abs(near - body) <= 0.5:
        body = float(near)
    srs = [s["sr"] for s in seg_info if s["sr"] and s["nchars"] >= 8]
    sr_body = median(srs) if srs else None

    for s in seg_info:
        size = snap_size(s["em"] * px2pt, body, short=len(s["items"]) <= 3)
        bold = bool(sr_body and s["sr"] and s["sr"] > sr_body * 1.28)
        its = s["items"]
        line = {
            "words": [(it["text"], it["ix0"] * px2pt, it["ix1"] * px2pt) for it in its],
            "x0": its[0]["ix0"] * px2pt, "x1": its[-1]["ix1"] * px2pt,
            "top": min(it["top"] for it in its) * px2pt, "base": s["base"] * px2pt,
            "size": size, "bold": bold, "text": " ".join(it["text"] for it in its),
        }
        sp.lines.append(line)

    _classify_alignment(sp)
    sp.lines.sort(key=lambda l: (round(l["base"], 1), l["x0"]))
    sp.plain_text = "\n".join(l["text"] for l in sp.lines)
    odoc.close()
    progress(1.0)
    return sp


class ScannedPageRotated:
    """Envoltura para analizar una página girada en cuartos de vuelta."""

    def __init__(self, page, q):
        self.page, self.q = page, q


def analyze_rotated(wrapper, dpi, q, progress):
    page = wrapper.page
    tmp = pymupdf.open()
    tmp.insert_pdf(page.parent, from_page=page.number, to_page=page.number)
    tp = tmp[0]
    tp.set_rotation((tp.rotation + 90 * q) % 360)
    res = analyze_page(tp, dpi, fix_orientation=False, progress=progress)
    res.quarter = q
    return res


_LIST_RE = re.compile(r"^\s*(\d{1,2}[\.\)]|[a-zA-Z][\.\)]|[•●▪■◦\-–—»])\s")


def _classify_alignment(sp: ScannedPage):
    lines = [l for l in sp.lines if l["x1"] - l["x0"] > 10]
    if not lines:
        return
    long_lines = [l for l in lines if (l["x1"] - l["x0"]) > 0.45 * sp.width] or lines
    xs0 = sorted(round(l["x0"]) for l in long_lines)
    xs1 = sorted(l["x1"] for l in long_lines)
    left = xs0[max(0, len(xs0) // 10)]
    right = xs1[min(len(xs1) - 1, int(len(xs1) * 0.9))]
    mid = (left + right) / 2
    width = max(1.0, right - left)
    for l in sp.lines:
        c = (l["x0"] + l["x1"]) / 2
        if l["x1"] >= right - 2.5 and l["x0"] <= left + 0.2 * width and len(l["words"]) > 2:
            l["align"] = "full"
        elif abs(c - mid) <= max(4.0, 0.025 * width) and l["x0"] > left + 12 and l["x1"] < right - 12:
            l["align"] = "center"
        elif l["x1"] >= right - 3 and l["x0"] > mid:
            l["align"] = "right"
        else:
            l["align"] = "left"
    # Ajustar bordes: el OCR deja pequeñas diferencias (±1-2 pt) entre renglones
    counts = {}
    for l in sp.lines:
        if l["align"] in ("left", "full"):
            k = round(l["x0"])
            counts[k] = counts.get(k, 0) + 1
    centers = []
    for k in sorted(counts, key=counts.get, reverse=True):
        if all(abs(k - c) > 3 for c in centers):
            centers.append(k)
    for l in sp.lines:
        if l["align"] in ("left", "full"):
            near = [c for c in centers if abs(l["x0"] - c) <= 3.0]
            if near:
                cands = [x for x in (l2["x0"] for l2 in sp.lines if l2["align"] in ("left", "full"))
                         if abs(x - near[0]) <= 3.0]
                target = median(cands)
                shift = target - l["x0"]
                l["x0"] = target
                if l["align"] == "left" and l["words"]:
                    t, a, b = l["words"][0]
                    l["words"][0] = (t, a + shift, b + shift)
        if l["align"] == "full":
            l["x1"] = right
    # listas y bloques alineados a la izquierda que parecen centrados
    ordered = sorted(sp.lines, key=lambda l: l["base"])
    for i, l in enumerate(ordered):
        if l["align"] != "center":
            continue
        if _LIST_RE.match(l["text"]):
            l["align"] = "left"
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(ordered):
                n = ordered[j]
                if abs(n["base"] - l["base"]) < 2.6 * l["size"] and abs(n["x0"] - l["x0"]) < 2.0 \
                        and abs(n["x1"] - l["x1"]) > 6:
                    l["align"] = "left"
                    break


def build_page(doc: pymupdf.Document, sp: ScannedPage, font_family: str = "Arial") -> pymupdf.Page:
    """Agrega al documento una página PDF reconstruida a partir del análisis."""
    page = doc.new_page(width=sp.width, height=sp.height)
    for rect, png in sp.images:
        try:
            page.insert_image(rect, stream=png)
        except Exception:
            pass
    regular, bold = get_fonts(font_family)
    tw_lines = pymupdf.TextWriter(page.rect)
    shape = page.new_shape()
    for x0, y, x1, t in sp.hrules:
        touches = any(x0 - 3 <= vx <= x1 + 3 and vy0 - 3 <= y <= vy1 + 3 for vx, vy0, vy1, _ in sp.vrules)
        if not touches:
            # línea suelta (por ejemplo, para firmar): se convierte en guiones bajos editables
            fs = 11
            uw = regular.text_length("_", fontsize=fs)
            n = max(3, int(round((x1 - x0) / uw)))
            tw_lines.append((x0, y), "_" * n, font=regular, fontsize=fs)
            continue
        shape.draw_line((x0, y), (x1, y))
        shape.finish(color=(0, 0, 0), width=min(t, 2.0))
    for x, y0, y1, t in sp.vrules:
        shape.draw_line((x, y0), (x, y1))
        shape.finish(color=(0, 0, 0), width=min(t, 2.0))
    shape.commit()
    tw_lines.write_text(page)

    tw = pymupdf.TextWriter(page.rect)
    for l in sp.lines:
        font = bold if l["bold"] else regular
        fs = l["size"]
        words = l["words"]
        widths = [font.text_length(w[0], fontsize=fs) for w in words]
        space = font.text_length(" ", fontsize=fs)
        natural = sum(widths) + space * (len(words) - 1)
        align = l.get("align", "left")
        xs = []
        if align == "full" and len(words) > 1:
            avail = l["x1"] - l["x0"]
            if sum(widths) + space * 0.2 * (len(words) - 1) > avail:
                # el renglón no entra con esta fuente: reducir un poco la letra solo aquí
                factor = max(0.88, avail / (sum(widths) + space * 0.6 * (len(words) - 1)))
                fs = round(fs * factor * 2) / 2
                widths = [font.text_length(w[0], fontsize=fs) for w in words]
                space = font.text_length(" ", fontsize=fs)
            gap = (avail - sum(widths)) / (len(words) - 1)
            gap = max(gap, space * 0.2)
            x = l["x0"]
            for wdt in widths:
                xs.append(x)
                x += wdt + gap
        elif align == "center":
            x = (l["x0"] + l["x1"]) / 2 - natural / 2
            for wdt in widths:
                xs.append(x)
                x += wdt + space
        elif align == "right":
            x = l["x1"] - natural
            for wdt in widths:
                xs.append(x)
                x += wdt + space
        else:
            prev_end = -1e9
            for (txt, wx0, wx1), wdt in zip(words, widths):
                x = max(wx0, prev_end + space * 0.9)
                xs.append(x)
                prev_end = x + wdt
        last = len(words) - 1
        for k, ((txt, _, _), x) in enumerate(zip(words, xs)):
            try:
                tw.append((x, l["base"]), txt + (" " if k < last else ""), font=font, fontsize=fs)
            except Exception:
                pass
    tw.write_text(page)
    return page


_ROMANS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV"]
_ROMAN_LIKE = re.compile(r"^([IVXl1!|]{1,4})\.$")


def fix_roman_headings(pages):
    """Corrige numerales romanos de títulos mal leídos (p. ej. «11.» -> «III.») usando la secuencia."""
    last = 0
    for sp in pages:
        for l in sorted(sp.lines, key=lambda x: x["base"]):
            if not l["words"] or l.get("align") == "center":
                continue
            first = l["words"][0][0]
            m = _ROMAN_LIKE.match(first)
            if not m:
                continue
            token = m.group(1)
            if token in _ROMANS:
                if l["bold"] or _ROMANS.index(token) + 1 == last + 1:
                    last = _ROMANS.index(token) + 1
                continue
            if not l["bold"] or last >= len(_ROMANS):
                continue
            new = _ROMANS[last] + "."
            last += 1
            t, a, b = l["words"][0]
            l["words"][0] = (new, a, b)
            l["text"] = new + l["text"][len(first):]
