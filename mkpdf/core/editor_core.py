"""Motor del editor: corregir texto existente y aplicar al PDF lo que se agregó en pantalla."""
import os
import re
import sys
from datetime import datetime

import pymupdf

from .common import open_pdf

# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------
_WIN = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_LIN = "/usr/share/fonts/truetype"

FONT_FILES = {
    # familia: (normal, negrita, cursiva, negrita cursiva) en Windows
    "Arial": ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    "Times New Roman": ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf", "calibrii.ttf", "calibriz.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf", "verdanai.ttf", "verdanaz.ttf"),
    "Tahoma": ("tahoma.ttf", "tahomabd.ttf", "tahoma.ttf", "tahomabd.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf", "georgiai.ttf", "georgiaz.ttf"),
    "Courier New": ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
}
_LINUX = {
    "Arial": ("liberation/LiberationSans-Regular.ttf", "liberation/LiberationSans-Bold.ttf",
              "liberation/LiberationSans-Italic.ttf", "liberation/LiberationSans-BoldItalic.ttf"),
    "Times New Roman": ("liberation/LiberationSerif-Regular.ttf", "liberation/LiberationSerif-Bold.ttf",
                        "liberation/LiberationSerif-Italic.ttf", "liberation/LiberationSerif-BoldItalic.ttf"),
    "Calibri": ("crosextra/Carlito-Regular.ttf", "crosextra/Carlito-Bold.ttf",
                "crosextra/Carlito-Italic.ttf", "crosextra/Carlito-BoldItalic.ttf"),
    "Courier New": ("liberation/LiberationMono-Regular.ttf", "liberation/LiberationMono-Bold.ttf",
                    "liberation/LiberationMono-Italic.ttf", "liberation/LiberationMono-BoldItalic.ttf"),
}
_BASE14 = {"Times New Roman": ("tiro", "tibo", "tiit", "tibi"), "Courier New": ("cour", "cobo", "coit", "cobi")}
EDITOR_FONTS = ["Arial", "Times New Roman", "Calibri", "Verdana", "Tahoma", "Georgia", "Courier New"]
_cache = {}


def font_for(family: str, bold=False, italic=False) -> pymupdf.Font:
    fam = family if family in FONT_FILES else "Arial"
    idx = (1 if bold else 0) + (2 if italic else 0)
    key = (fam, idx)
    if key in _cache:
        return _cache[key]
    candidates = [os.path.join(_WIN, FONT_FILES[fam][idx])]
    if fam in _LINUX:
        candidates.append(os.path.join(_LIN, _LINUX[fam][idx]))
    candidates.append(os.path.join(_WIN, FONT_FILES["Arial"][idx]))
    candidates.append(os.path.join(_LIN, _LINUX["Arial"][idx]))
    font = None
    for c in candidates:
        if os.path.isfile(c):
            try:
                font = pymupdf.Font(fontfile=c)
                break
            except Exception:
                pass
    if font is None:
        base = _BASE14.get(fam, ("helv", "hebo", "heit", "hebi"))[idx]
        font = pymupdf.Font(base)
    _cache[key] = font
    return font


def guess_family(fontname: str):
    """'ABCDEF+Arial-BoldMT' -> ('Arial', True, False)"""
    n = re.sub(r"^[A-Z]{6}\+", "", fontname or "")
    low = n.lower().replace(" ", "").replace("-", "").replace(",", "")
    bold = any(k in low for k in ("bold", "black", "heavy", "semibold")) or low.endswith(("bd", "mtbd"))
    italic = "italic" in low or "oblique" in low
    table = (("arial", "Arial"), ("helvetica", "Arial"), ("liberationsans", "Arial"), ("timesnewroman", "Times New Roman"),
             ("times", "Times New Roman"), ("liberationserif", "Times New Roman"), ("calibri", "Calibri"),
             ("carlito", "Calibri"), ("verdana", "Verdana"), ("tahoma", "Tahoma"), ("georgia", "Georgia"),
             ("courier", "Courier New"), ("cambria", "Times New Roman"), ("garamond", "Times New Roman"),
             ("bookantiqua", "Times New Roman"), ("century", "Arial"), ("segoe", "Arial"), ("trebuchet", "Verdana"))
    for k, fam in table:
        if k in low:
            return fam, bold, italic
    return "Arial", bold, italic


def int_to_rgb(c: int):
    return ((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0


# ---------------------------------------------------------------------------
# Documento de trabajo
# ---------------------------------------------------------------------------

def open_working(path: str) -> pymupdf.Document:
    src = open_pdf(path)
    doc = pymupdf.open("pdf", src.tobytes())   # copia en memoria: el original no se toca
    src.close()
    for page in doc:
        if page.rotation:
            try:
                page.remove_rotation()
            except Exception:
                pass
    return doc


def has_text(page: pymupdf.Page) -> bool:
    return len(page.get_text("text").strip()) > 10


# ---------------------------------------------------------------------------
# Corregir texto existente
# ---------------------------------------------------------------------------

def text_segments(page: pymupdf.Page):
    """Tramos de texto con el mismo estilo dentro de cada renglón (para poder corregirlos)."""
    d = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)
    segs = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            if abs(l["dir"][1]) > 0.02 or l["dir"][0] < 0:
                continue
            cur = None
            for s in l["spans"]:
                chars = s.get("chars", [])
                if not chars:
                    continue
                style = (s["font"], round(s["size"], 1), s["color"], s["flags"] & (16 | 2))
                text = "".join(c["c"] for c in chars)
                if cur and cur["style"] == style:
                    cur["chars"] += chars
                    cur["text"] += text
                else:
                    if cur:
                        segs.append(cur)
                    cur = {"style": style, "font": s["font"], "size": s["size"], "color": s["color"],
                           "flags": s["flags"], "origin": tuple(chars[0]["origin"]), "chars": list(chars),
                           "text": text, "ascender": s.get("ascender", 0.9), "descender": s.get("descender", -0.2)}
            if cur:
                segs.append(cur)
    out = []
    for s in segs:
        if not s["text"].strip():
            continue
        # quitar espacios de los extremos
        chars = s["chars"]
        while chars and not chars[0]["c"].strip():
            chars = chars[1:]
        while chars and not chars[-1]["c"].strip():
            chars = chars[:-1]
        if not chars:
            continue
        r = pymupdf.Rect(chars[0]["bbox"])
        for c in chars[1:]:
            r |= pymupdf.Rect(c["bbox"])
        base_y = chars[0]["origin"][1]
        top = base_y - s["size"] * max(0.7, s["ascender"])
        bot = base_y - s["size"] * min(-0.1, s["descender"])
        out.append({"rect": (r.x0, top, r.x1, bot), "text": "".join(c["c"] for c in chars),
                    "font": s["font"], "size": s["size"], "color": s["color"], "flags": s["flags"],
                    "origin": (chars[0]["origin"][0], base_y),
                    "char_rects": [tuple(c["bbox"]) for c in chars]})
    return out


def replace_segment(doc: pymupdf.Document, page_no: int, seg: dict, new_text: str,
                    family: str = None, size: float = None, bold=None, color=None):
    """Borra el tramo original y escribe el texto nuevo en el mismo lugar y con el mismo estilo."""
    page = doc[page_no]
    x0, top, x1, bot = seg["rect"]
    h = bot - top
    # zona a borrar: un poco más angosta en altura para no tocar renglones vecinos
    r = pymupdf.Rect(x0 + 0.3, top + h * 0.28, x1 - 0.3, bot - h * 0.28)
    page.add_redact_annot(r)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                          text=getattr(pymupdf, "PDF_REDACT_TEXT_REMOVE", 0))
    if not new_text.strip():
        return
    fam, gbold, italic = guess_family(seg["font"])
    if family:
        fam = family
    is_bold = gbold or bool(seg["flags"] & 16) if bold is None else bold
    is_italic = italic or bool(seg["flags"] & 2)
    font = font_for(fam, is_bold, is_italic)
    fs = size or seg["size"]
    col = color if color is not None else int_to_rgb(seg["color"])
    tw = pymupdf.TextWriter(page.rect, color=col)
    tw.append(seg["origin"], new_text, font=font, fontsize=fs)
    tw.write_text(page)


def page_snapshot(doc: pymupdf.Document, page_no: int) -> bytes:
    tmp = pymupdf.open()
    tmp.insert_pdf(doc, from_page=page_no, to_page=page_no, annots=True, links=True, widgets=True)
    data = tmp.tobytes()
    tmp.close()
    return data


def restore_page(doc: pymupdf.Document, page_no: int, data: bytes):
    tmp = pymupdf.open("pdf", data)
    doc.delete_page(page_no)
    doc.insert_pdf(tmp, from_page=0, to_page=0, start_at=page_no, annots=True, links=True, widgets=True)
    tmp.close()


# ---------------------------------------------------------------------------
# Sello «Recibido»
# ---------------------------------------------------------------------------

def stamp_layout(rect, title, lines):
    """Posiciones del contenido del sello dentro de su rectángulo (compartido con la pantalla)."""
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    rows = [(title, True)] + [(l, False) for l in lines if l is not None]
    weights = [1.55] + [1.0] * (len(rows) - 1)
    unit = h / (sum(weights) * 1.32 + 1.1)
    out = []
    y = y0 + unit * 0.6
    for (txt, bold), wgt in zip(rows, weights):
        size = unit * wgt
        y += size * 1.0
        out.append({"text": txt, "bold": bold, "size": size, "baseline": y, "cx": (x0 + x1) / 2})
        y += size * 0.32
    return out


def default_stamp_lines(area: str, with_date=True, with_fields=True, when: datetime = None):
    when = when or datetime.now()
    lines = []
    if area:
        lines.append(area)
    if with_date:
        lines.append(when.strftime("Fecha: %d/%m/%Y   Hora: %H:%M"))
    if with_fields:
        lines.append("Folios: _____  Firma: _________")
    return lines


# ---------------------------------------------------------------------------
# Aplicar los cambios al guardar
# ---------------------------------------------------------------------------

def _fit_font(text, font, size, max_w):
    w = font.text_length(text, fontsize=size)
    if w > max_w > 0:
        return size * max_w / w
    return size


def bake(doc: pymupdf.Document, specs: list, fields: list = None):
    """Escribe en el PDF lo agregado en el editor. specs: lista de dict (ver editor.py)."""
    by_page = {}
    for sp in specs:
        by_page.setdefault(sp["page"], []).append(sp)
    for page_no, items in by_page.items():
        page = doc[page_no]
        # 1) Tapar: borrado real de lo que hay debajo
        redacts = [it for it in items if it["type"] == "redact"]
        if redacts:
            for it in redacts:
                page.add_redact_annot(pymupdf.Rect(it["rect"]), fill=(1, 1, 1))
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                                  graphics=getattr(pymupdf, "PDF_REDACT_LINE_ART_REMOVE_IF_COVERED", 2))
        # 2) Contenido
        for it in items:
            t = it["type"]
            if t == "rect":
                page.draw_rect(pymupdf.Rect(it["rect"]), color=it["color"], width=it["width"], overlay=True)
            elif t == "line":
                page.draw_line(it["p1"], it["p2"], color=it["color"], width=it["width"], overlay=True)
            elif t == "ink":
                shape = page.new_shape()
                for stroke in it["strokes"]:
                    if len(stroke) >= 2:
                        shape.draw_polyline(stroke)
                    elif len(stroke) == 1:
                        x, y = stroke[0]
                        shape.draw_circle((x, y), it["width"] / 2)
                shape.finish(color=it["color"], width=it["width"], closePath=False,
                             lineCap=1, lineJoin=1)
                shape.commit(overlay=True)
            elif t == "image":
                page.insert_image(pymupdf.Rect(it["rect"]), stream=it["png"], keep_proportion=False, overlay=True)
            elif t == "text":
                font = font_for(it["font"], it.get("bold"), it.get("italic"))
                tw = pymupdf.TextWriter(page.rect, color=it["color"])
                for x, y, txt in it["lines"]:
                    if txt:
                        tw.append((x, y), txt, font=font, fontsize=it["size"])
                tw.write_text(page)
            elif t == "stamp":
                r = pymupdf.Rect(it["rect"])
                col = it["color"]
                page.draw_rect(r, color=col, width=max(1.0, r.height * 0.018), radius=0.06, overlay=True)
                inner = r + (r.height * 0.035, r.height * 0.035, -r.height * 0.035, -r.height * 0.035)
                page.draw_rect(inner, color=col, width=max(0.5, r.height * 0.007), radius=0.06, overlay=True)
                tw = pymupdf.TextWriter(page.rect, color=col)
                for row in stamp_layout(tuple(r), it["title"], it["lines"]):
                    f = font_for("Arial", row["bold"])
                    size = _fit_font(row["text"], f, row["size"], r.width * 0.9)
                    w = f.text_length(row["text"], fontsize=size)
                    tw.append((row["cx"] - w / 2, row["baseline"]), row["text"], font=f, fontsize=size)
                tw.write_text(page)
        # 3) Anotaciones (se ven y se pueden quitar en cualquier lector de PDF)
        for it in items:
            t = it["type"]
            if t in ("highlight", "underline", "strike"):
                rects = [pymupdf.Rect(r) for r in it["rects"]]
                if not rects:
                    continue
                if t == "highlight":
                    a = page.add_highlight_annot(rects)
                elif t == "underline":
                    a = page.add_underline_annot(rects)
                else:
                    a = page.add_strikeout_annot(rects)
                a.set_colors(stroke=it["color"])
                a.update()
            elif t == "note":
                a = page.add_text_annot(it["point"], it["text"], icon="Comment")
                a.set_colors(stroke=(1, 0.82, 0.2))
                a.set_info(title=it.get("author") or "MK PDF Studio")
                a.update()
    # 4) Formularios
    for f in fields or []:
        try:
            page = doc[f["page"]]
            for w in page.widgets():
                if w.xref == f["xref"]:
                    if w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
                        w.field_value = w.on_state() if f["value"] else "Off"
                    elif w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                        w.field_value = bool(f["value"])
                    else:
                        w.field_value = f["value"]
                    w.update()
                    break
        except Exception:
            pass


def save_copy(doc: pymupdf.Document, specs, fields, dst: str):
    out = pymupdf.open("pdf", doc.tobytes())
    try:
        bake(out, specs, fields)
        out.save(dst, garbage=3, deflate=True)
    finally:
        out.close()


# ---------------------------------------------------------------------------
# Firmas y sellos guardados
# ---------------------------------------------------------------------------

def signatures_dir():
    from ..config import user_data_dir
    d = os.path.join(user_data_dir(), "firmas")
    os.makedirs(d, exist_ok=True)
    return d


def _unique_png(base):
    base = re.sub(r"[^\w\- áéíóúñÁÉÍÓÚÑ]", "", base).strip() or "firma"
    dst = os.path.join(signatures_dir(), base + ".png")
    i = 1
    while os.path.exists(dst):
        dst = os.path.join(signatures_dir(), f"{base} ({i}).png")
        i += 1
    return dst


def save_signature_rgba(rgba, name: str, width_cm: float = None) -> str:
    from . import bgremove
    dst = _unique_png(name)
    bgremove.save_png(rgba, dst)
    if width_cm:
        set_signature_width(dst, width_cm)
    return dst


def import_signature(path: str, remove_white=True, name: str = None) -> str:
    """Guarda una imagen de firma o sello en la biblioteca (PNG con fondo transparente)."""
    import numpy as np
    from PIL import Image, ImageOps
    from . import bgremove
    if remove_white:
        rgba = bgremove.process_file(path, max_side=1600)
    else:
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
        im.thumbnail((1600, 1600), Image.LANCZOS)
        rgba = np.asarray(im).copy()
    base = name or os.path.splitext(os.path.basename(path))[0]
    return save_signature_rgba(rgba, base)


def _meta_path(png_path):
    return os.path.splitext(png_path)[0] + ".json"


def signature_width(png_path, default=5.0) -> float:
    import json
    try:
        with open(_meta_path(png_path), "r", encoding="utf-8") as f:
            return float(json.load(f).get("width_cm", default))
    except Exception:
        return default


def set_signature_width(png_path, width_cm: float):
    import json
    try:
        with open(_meta_path(png_path), "w", encoding="utf-8") as f:
            json.dump({"width_cm": round(float(width_cm), 2)}, f)
    except Exception:
        pass


def delete_signature(png_path):
    for p in (png_path, _meta_path(png_path)):
        try:
            os.remove(p)
        except Exception:
            pass


def list_signatures():
    d = signatures_dir()
    files = [os.path.join(d, f) for f in os.listdir(d) if f.lower().endswith(".png")]
    return sorted(files, key=os.path.getmtime, reverse=True)
