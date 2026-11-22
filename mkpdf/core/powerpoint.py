"""PDF a PowerPoint.

Modo editable: cada página es una diapositiva con el fondo (imágenes, líneas, colores) como
imagen y el texto en cuadros de texto que se pueden modificar, en la misma posición.
Modo imagen: cada página como una imagen idéntica al PDF.
"""
import io
import re
from statistics import median

import pymupdf
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Emu, Pt

from . import scanlayout
from .common import NULL_PROGRESS, UserError, open_pdf, page_kind
from ..config import settings

EMU_PER_PT = 12700
MAX_SLIDE_PT = 56 * 72  # límite de PowerPoint: 56 pulgadas


def _font_family(name: str):
    n = re.sub(r"^[A-Z]{6}\+", "", name or "")
    low = n.lower().replace(" ", "").replace("-", "")
    bold = any(k in low for k in ("bold", "black", "heavy", "semibold", ",bd", "bd"))
    italic = "italic" in low or "oblique" in low
    for key, fam in (("arial", "Arial"), ("helvetica", "Arial"), ("liberationsans", "Arial"),
                     ("timesnewroman", "Times New Roman"), ("times", "Times New Roman"),
                     ("liberationserif", "Times New Roman"), ("calibri", "Calibri"), ("carlito", "Calibri"),
                     ("cambria", "Cambria"), ("verdana", "Verdana"), ("tahoma", "Tahoma"),
                     ("georgia", "Georgia"), ("garamond", "Garamond"), ("bookantiqua", "Book Antiqua"),
                     ("century", "Century Gothic"), ("trebuchet", "Trebuchet MS"), ("segoe", "Segoe UI"),
                     ("courier", "Courier New"), ("symbol", "Symbol"), ("wingdings", "Wingdings")):
        if key in low:
            return fam, bold, italic
    base = re.split(r"[-,]", n)[0] or "Arial"
    return base, bold, italic


def _background_png(page: pymupdf.Page, dpi: int) -> bytes:
    """Imagen de la página sin el texto (se queda todo lo demás)."""
    doc = page.parent
    tmp = pymupdf.open()
    tmp.insert_pdf(doc, from_page=page.number, to_page=page.number)
    p = tmp[0]
    if p.rotation:
        p.remove_rotation()
    try:
        p.add_redact_annot(p.rect)
        p.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                           graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                           text=getattr(pymupdf, "PDF_REDACT_TEXT_REMOVE", 0))
    except Exception:
        pass
    pix = p.get_pixmap(dpi=dpi, alpha=False)
    data = pix.tobytes("png")
    tmp.close()
    return data


def _page_png(page: pymupdf.Page, dpi: int) -> bytes:
    return page.get_pixmap(dpi=dpi, alpha=False).tobytes("png")


def _lines(page: pymupdf.Page):
    """Agrupa el texto de la página en párrafos según su posición (no según el orden interno del PDF)."""
    d = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP)
    raw = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            if abs(l["dir"][1]) > 0.05:
                continue  # texto inclinado o vertical: queda en el fondo
            spans = [s for s in l["spans"] if s["text"]]
            if not spans or not "".join(s["text"] for s in spans).strip():
                continue
            size = max(s["size"] for s in spans)
            raw.append({"bbox": pymupdf.Rect(l["bbox"]), "spans": spans, "size": size,
                        "base": median(s["origin"][1] for s in spans)})
    # 1) renglones: partes en la misma línea base y cercanas entre sí
    raw.sort(key=lambda l: (round(l["base"]), l["bbox"].x0))
    rows = []
    for l in raw:
        merged = False
        for r in reversed(rows[-8:]):
            if abs(r["base"] - l["base"]) <= 0.3 * max(r["size"], l["size"]):
                gap = l["bbox"].x0 - r["bbox"].x1
                if -2 <= gap <= 1.6 * max(r["size"], l["size"]):
                    r["spans"] = r["spans"] + l["spans"]
                    r["bbox"] = r["bbox"] | l["bbox"]
                    r["size"] = max(r["size"], l["size"])
                    merged = True
                    break
        if not merged:
            rows.append(dict(l))
    # 2) párrafos: renglones seguidos, alineados y con el mismo tamaño de letra
    rows.sort(key=lambda r: (r["base"], r["bbox"].x0))
    paras = []
    for r in rows:
        target = None
        for p in reversed(paras[-12:]):
            last = p["lines"][-1]
            gap = r["base"] - last["base"]
            if not (0.8 * r["size"] <= gap <= 1.75 * max(r["size"], last["size"])):
                continue
            if abs(r["size"] - last["size"]) > 0.8:
                continue
            px0, px1 = p["x0"], p["x1"]
            ov = min(px1, r["bbox"].x1) - max(px0, r["bbox"].x0)
            if ov < 0.5 * min(r["bbox"].width, px1 - px0):
                continue
            if r["bbox"].x0 < px0 - 3 and len(p["lines"]) > 1:
                continue
            target = p
            break
        if target is None:
            paras.append({"lines": [r], "x0": r["bbox"].x0, "x1": r["bbox"].x1})
        else:
            target["lines"].append(r)
            target["x0"] = min(target["x0"], r["bbox"].x0)
            target["x1"] = max(target["x1"], r["bbox"].x1)
    return paras


def _add_textbox(slide, block, sx, sy, ox, oy):
    lines = block["lines"]
    x0 = min(l["bbox"].x0 for l in lines)
    x1 = max(l["bbox"].x1 for l in lines)
    y0 = min(l["bbox"].y0 for l in lines)
    y1 = max(l["bbox"].y1 for l in lines)
    w = (x1 - x0) * 1.04 + 4
    sizes = [s["size"] for l in lines for s in l["spans"]]
    main_size = median(sizes) if sizes else 11
    # alineación del bloque
    align = PP_ALIGN.LEFT
    if len(lines) > 1:
        centers = [(l["bbox"].x0 + l["bbox"].x1) / 2 for l in lines]
        lefts = [l["bbox"].x0 for l in lines]
        rights = [l["bbox"].x1 for l in lines]
        if max(centers) - min(centers) < 2.5 and max(lefts) - min(lefts) > 4:
            align = PP_ALIGN.CENTER
        elif max(rights) - min(rights) < 2 and max(lefts) - min(lefts) > 4:
            align = PP_ALIGN.RIGHT
    tb = slide.shapes.add_textbox(Emu(int((ox + x0 * sx) * EMU_PER_PT)), Emu(int((oy + y0 * sy) * EMU_PER_PT)),
                                  Emu(int(w * sx * EMU_PER_PT)), Emu(int(max(4, y1 - y0) * sy * EMU_PER_PT)))
    tf = tb.text_frame
    tf.word_wrap = False
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP
    bases = [l["base"] for l in lines]
    gaps = [b - a for a, b in zip(bases, bases[1:]) if b - a > 0]
    for k, l in enumerate(lines):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.alignment = align
        lsz = max(s["size"] for s in l["spans"])
        if k == 0:
            p.line_spacing = Pt(lsz * 1.17 * sy)
        else:
            gap = bases[k] - bases[k - 1]
            p.line_spacing = Pt(max(lsz, gap) * sy) if gap > 0 else Pt(lsz * 1.17 * sy)
        if align == PP_ALIGN.LEFT:
            indent = l["bbox"].x0 - x0
            if indent > 0.5:
                pPr = p._p.get_or_add_pPr()
                pPr.set("marL", str(int(indent * sx * EMU_PER_PT)))
        prev_end = None
        for s in l["spans"]:
            text = s["text"]
            # espacios grandes entre partes del mismo renglón (columnas): conservar separación
            if prev_end is not None and not text.startswith(" ") and not (p.runs and p.runs[-1].text.endswith(" ")):
                gap = s["bbox"][0] - prev_end
                if gap > s["size"] * 0.18:
                    n = max(1, int(round(gap / max(1.0, s["size"] * 0.28))))
                    text = " " * min(n, 40) + text
            prev_end = s["bbox"][2]
            r = p.add_run()
            r.text = text
            fam, bold, italic = _font_family(s["font"])
            f = r.font
            f.name = fam
            f.size = Pt(round(s["size"] * sy * 2) / 2)
            f.bold = bold or bool(s["flags"] & 16)
            f.italic = italic or bool(s["flags"] & 2)
            c = s.get("color", 0) or 0
            f.color.rgb = RGBColor((c >> 16) & 255, (c >> 8) & 255, c & 255)
    return tb


def pdf_to_powerpoint(src: str, dst: str, pages=None, mode: str = "editable", progress=NULL_PROGRESS) -> dict:
    doc = open_pdf(src)
    idx = pages if pages else list(range(len(doc)))
    if not idx:
        raise UserError("El documento no tiene páginas.")
    first = doc[idx[0]].rect
    scale0 = min(1.0, MAX_SLIDE_PT / max(first.width, first.height))
    SW, SH = first.width * scale0, first.height * scale0
    prs = Presentation()
    prs.slide_width = Emu(int(SW * EMU_PER_PT))
    prs.slide_height = Emu(int(SH * EMU_PER_PT))
    blank = prs.slide_layouts[6]
    font = settings().get("scan_font") or "Arial"
    n = len(idx)
    scanned_count = 0
    work = pymupdf.open()
    analyzed = {}
    if mode == "editable":
        for k, i in enumerate(idx):
            if page_kind(doc[i]) == "escaneada":
                progress(0.02 + 0.8 * k / n, f"Reconociendo texto (OCR): página {k + 1} de {n}")
                analyzed[i] = scanlayout.analyze_page(doc[i], progress=progress.sub(0.02 + 0.8 * k / n,
                                                                                    0.02 + 0.8 * (k + 1) / n))
        scanlayout.fix_roman_headings([analyzed[i] for i in idx if i in analyzed])
        scanned_count = len(analyzed)
    for k, i in enumerate(idx):
        progress(0.82 + 0.12 * k / n, f"Creando diapositiva {k + 1} de {n}")
        page = doc[i]
        src_page = page
        if i in analyzed:
            src_page = scanlayout.build_page(work, analyzed[i], font)
        r = src_page.rect
        s = min(SW / r.width, SH / r.height)
        ox, oy = (SW - r.width * s) / 2, (SH - r.height * s) / 2
        slide = prs.slides.add_slide(blank)
        if mode == "imagen":
            png = _page_png(page, 200)
        else:
            png = _background_png(src_page, 170)
        slide.shapes.add_picture(io.BytesIO(png), Emu(int(ox * EMU_PER_PT)), Emu(int(oy * EMU_PER_PT)),
                                 Emu(int(r.width * s * EMU_PER_PT)), Emu(int(r.height * s * EMU_PER_PT)))
        if mode != "imagen":
            tmp_rot = None
            tp = src_page
            if tp.rotation:
                tmp_rot = pymupdf.open()
                tmp_rot.insert_pdf(tp.parent, from_page=tp.number, to_page=tp.number)
                tp = tmp_rot[0]
                tp.remove_rotation()
            for block in _lines(tp):
                try:
                    _add_textbox(slide, block, s, s, ox, oy)
                except Exception:
                    pass
            if tmp_rot:
                tmp_rot.close()
    progress(0.95, "Guardando la presentación…")
    prs.save(dst)
    work.close()
    doc.close()
    progress(1.0, "Listo")
    return {"pages": n, "scanned": scanned_count}
