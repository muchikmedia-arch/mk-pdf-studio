"""PDF escaneado -> PDF con texto buscable y copiable; imagen -> texto."""
import os
import re

import cv2
import numpy as np
import pymupdf

from . import ocr
from .common import NULL_PROGRESS, open_pdf, page_kind, save_pdf


_ASCII_PUNCT = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-", "•": "-", "…": "..."})


def _add_text_layer(page: pymupdf.Page, dpi: int):
    """Agrega texto invisible sobre la imagen del escaneo, palabra por palabra."""
    rgb = ocr.render_rgb(page, dpi)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clean = ocr.normalize_background(gray)
    odoc, opage = ocr.ocr_gray(clean, dpi)
    words = ocr.ocr_words(opage)
    sx = page.rect.width / opage.rect.width
    sy = page.rect.height / opage.rect.height
    font = pymupdf.Font("helv")
    derot = page.derotation_matrix
    count = 0
    for w in words:
        x0, y0, x1, y1 = w["bbox"]
        vis = pymupdf.Rect(x0 * sx, y0 * sy, x1 * sx, y1 * sy)
        h = vis.height
        if h <= 1 or vis.width <= 1:
            continue
        text = ocr.fix_text(w["text"]).translate(_ASCII_PUNCT)
        fs = max(4.0, h * 0.95)
        natural = font.text_length(text, fontsize=fs) or 1.0
        scale = vis.width / natural
        base_vis = pymupdf.Point(vis.x0, vis.y1 - h * 0.2)
        base = base_vis * derot
        mat = pymupdf.Matrix(scale, 1) * pymupdf.Matrix(page.rotation)
        try:
            page.insert_text(base, text, fontsize=fs, fontname="helv", render_mode=3,
                             morph=(base, mat))
            count += 1
        except Exception:
            pass
    odoc.close()
    return count


def make_searchable(src, dst, progress=NULL_PROGRESS) -> dict:
    doc = open_pdf(src)
    n = doc.page_count
    done = 0
    for i, page in enumerate(doc):
        progress(i / n, f"Reconociendo texto (OCR): página {i + 1} de {n}")
        if page_kind(page) == "escaneada":
            # si ya tenía texto invisible de otro OCR, se respeta
            if len(page.get_text().strip()) > 40:
                continue
            _add_text_layer(page, ocr.ocr_dpi())
            done += 1
    save_pdf(doc, dst)
    doc.close()
    progress(1.0, "Listo")
    return {"pages": n, "ocr_pages": done}


def _paragraphs_from_page(opage: pymupdf.Page) -> str:
    blocks = opage.get_text("blocks", sort=True)
    paras = []
    for b in blocks:
        if b[6] != 0:
            continue
        lines = [l.strip() for l in b[4].splitlines() if l.strip()]
        if not lines:
            continue
        text = ""
        for l in lines:
            l = ocr.fix_text(l)
            if text.endswith("-") and l[:1].islower():
                text = text[:-1] + l
            elif text:
                text += " " + l
            else:
                text = l
        paras.append(text)
    return "\n\n".join(paras)


def image_to_text(path: str, progress=NULL_PROGRESS) -> str:
    """Texto de una imagen (captura, foto, afiche)."""
    progress(0.1, "Preparando la imagen…")
    img = _prepared_image(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if max(h, w) < 1800:
        f = 1800.0 / max(h, w)
        gray = cv2.resize(gray, (int(w * f), int(h * f)), interpolation=cv2.INTER_CUBIC)
    # texto claro sobre fondo oscuro -> invertir
    if np.median(gray) < 110:
        gray = 255 - gray
    q = ocr.detect_orientation(gray)
    if q:
        gray = ocr.rotate90(gray, q)
    angle = ocr.estimate_skew(gray)
    if angle:
        gray = ocr.rotate_image(gray, angle)
    clean = ocr.normalize_background(gray)
    progress(0.4, "Reconociendo texto…")
    odoc, opage = ocr.ocr_gray(clean, 300)
    text = _paragraphs_from_page(opage)
    odoc.close()
    progress(1.0, "Listo")
    return text


def pdf_page_text(src: str, page_index: int) -> str:
    doc = open_pdf(src)
    page = doc[page_index]
    if page_kind(page) == "escaneada":
        clean, rgb, angle, q = ocr.prepare_page_image(page, 300)
        odoc, opage = ocr.ocr_gray(clean, 300)
        text = _paragraphs_from_page(opage)
        odoc.close()
    else:
        text = page.get_text()
    doc.close()
    return text


def _prepared_image(path: str):
    """Si es la foto de una hoja, la recorta y endereza; si es una captura, la deja igual."""
    from . import photoscan
    img = photoscan.load_photo(path)
    try:
        quad = photoscan.find_document(img)
        if quad is not None:
            img = photoscan.enhance(photoscan.warp_document(img, quad), "color")
    except Exception:
        pass
    return img


def image_to_pdf_for_ocr(path: str) -> pymupdf.Document:
    """Imagen -> PDF de una página (para convertirla luego a Word con OCR)."""
    img = _prepared_image(path)
    h, w = img.shape[:2]
    dpi = 300 if max(h, w) > 2500 else 200 if max(h, w) > 1500 else 150
    doc = pymupdf.open()
    page = doc.new_page(width=w * 72.0 / dpi, height=h * 72.0 / dpi)
    ok, data = cv2.imencode(".png", img)
    page.insert_image(page.rect, stream=data.tobytes())
    return doc
