"""Herramientas de oficina para PDF."""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata

import cv2
import numpy as np
import pymupdf

from . import ocr, photoscan
from .common import (EXCEL_EXT, IMAGE_EXT, NULL_PROGRESS, PDF_EXT, WORD_EXT, UserError, ext_of,
                     human_size, open_pdf, page_kind, parse_ranges, save_pdf, unique_path)

PAPER = {
    "A4": (595.28, 841.89),
    "Carta": (612.0, 792.0),
    "Oficio": (612.0, 936.0),     # 8.5 x 13 pulgadas
    "A3": (841.89, 1190.55),
    "A5": (419.53, 595.28),
}


# ---------------------------------------------------------------------------
# Utilidades de posición en páginas giradas
# ---------------------------------------------------------------------------

def _visual_rect(page):
    return page.rect  # PyMuPDF ya entrega el tamaño visible (con giro aplicado)


def _to_unrot(page, rect):
    return pymupdf.Rect(rect) * page.derotation_matrix


# ---------------------------------------------------------------------------
# Office -> PDF
# ---------------------------------------------------------------------------

def _find_soffice():
    for c in (shutil.which("soffice"), shutil.which("libreoffice"),
              r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if c and os.path.exists(c):
            return c
    return None


_PS_WORD = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($env:MK_SRC, $false, $true, $false)
  $d.ExportAsFixedFormat($env:MK_DST, 17)
  $d.Close(0)
} finally { $w.Quit() }
"""

_PS_EXCEL = r"""
$ErrorActionPreference = 'Stop'
$x = New-Object -ComObject Excel.Application
$x.Visible = $false
$x.DisplayAlerts = $false
try {
  $wb = $x.Workbooks.Open($env:MK_SRC, 0, $true)
  $wb.ExportAsFixedFormat(0, $env:MK_DST)
  $wb.Close($false)
} finally { $x.Quit() }
"""


def office_to_pdf(src: str, dst: str):
    """Convierte Word/Excel a PDF con el Office instalado (o LibreOffice si no hay Office)."""
    ext = ext_of(src)
    errors = []
    if sys.platform.startswith("win") and ext != ".odt" and ext != ".ods":
        script = _PS_WORD if ext in WORD_EXT else _PS_EXCEL
        env = dict(os.environ, MK_SRC=os.path.abspath(src), MK_DST=os.path.abspath(dst))
        try:
            flags = 0x08000000  # CREATE_NO_WINDOW
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                               env=env, capture_output=True, timeout=300, creationflags=flags)
            if r.returncode == 0 and os.path.exists(dst):
                return
            errors.append(r.stderr.decode("utf-8", "ignore")[:300])
        except Exception as e:
            errors.append(str(e))
    soffice = _find_soffice()
    if soffice:
        outdir = tempfile.mkdtemp(prefix="mkpdf_lo_")
        try:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", outdir, src],
                           capture_output=True, timeout=300,
                           creationflags=0x08000000 if sys.platform.startswith("win") else 0)
            produced = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0] + ".pdf")
            if os.path.exists(produced):
                shutil.move(produced, dst)
                return
        finally:
            shutil.rmtree(outdir, ignore_errors=True)
    raise UserError(f"No se pudo convertir «{os.path.basename(src)}» a PDF. "
                    "Para unir archivos de Word o Excel se necesita Microsoft Office (o LibreOffice) instalado.")


# ---------------------------------------------------------------------------
# Unir / armar expediente
# ---------------------------------------------------------------------------

def _image_page(out: pymupdf.Document, img_bgr: np.ndarray, paper: str = "A4", margin: float = 0, dpi_guess=200):
    h, w = img_bgr.shape[:2]
    ok, data = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    stream = data.tobytes()
    if paper in PAPER:
        pw, ph = PAPER[paper]
        if w > h:
            pw, ph = ph, pw
        page = out.new_page(width=pw, height=ph)
        area = pymupdf.Rect(margin, margin, pw - margin, ph - margin)
        page.insert_image(area, stream=stream, keep_proportion=True)
    else:
        pw, ph = w * 72.0 / dpi_guess, h * 72.0 / dpi_guess
        page = out.new_page(width=pw, height=ph)
        page.insert_image(page.rect, stream=stream)
    return page


def merge_files(files, dst, paper_for_images="A4", fit_all_a4=False, progress=NULL_PROGRESS):
    if not files:
        raise UserError("Agrega al menos un archivo.")
    out = pymupdf.open()
    tmpdir = tempfile.mkdtemp(prefix="mkpdf_merge_")
    try:
        n = len(files)
        for k, f in enumerate(files):
            progress(k / n, f"Agregando {os.path.basename(f)} ({k + 1} de {n})")
            ext = ext_of(f)
            if ext in PDF_EXT:
                src = open_pdf(f)
                out.insert_pdf(src)
                src.close()
            elif ext in IMAGE_EXT:
                img = photoscan.load_photo(f)
                _image_page(out, img, paper_for_images)
            elif ext in WORD_EXT or ext in EXCEL_EXT:
                tmp = os.path.join(tmpdir, f"{k}.pdf")
                office_to_pdf(f, tmp)
                src = pymupdf.open(tmp)
                out.insert_pdf(src)
                src.close()
            else:
                raise UserError(f"No sé cómo agregar el archivo «{os.path.basename(f)}».")
        if fit_all_a4:
            tmp = os.path.join(tmpdir, "unido.pdf")
            out.save(tmp)
            out.close()
            normalize_size(tmp, dst, "A4", progress=progress.sub(0.9, 1.0))
            return {"pages": pymupdf.open(dst).page_count}
        progress(0.95, "Guardando…")
        save_pdf(out, dst)
        return {"pages": out.page_count}
    finally:
        try:
            out.close()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Dividir
# ---------------------------------------------------------------------------

def split_pdf(src, outdir, mode="cada", every=1, ranges_text="", progress=NULL_PROGRESS):
    doc = open_pdf(src)
    n = doc.page_count
    if mode == "cada":
        groups = [[i] for i in range(n)]
    elif mode == "grupos":
        every = max(1, int(every))
        groups = [list(range(i, min(n, i + every))) for i in range(0, n, every)]
    else:
        groups = parse_ranges(ranges_text, n)
        if not groups:
            raise UserError("Escribe los rangos de páginas, por ejemplo: 1-3, 4-10")
    stem = os.path.splitext(os.path.basename(src))[0]
    folder = unique_path(os.path.join(outdir, f"{stem} - partes"))
    os.makedirs(folder, exist_ok=True)
    created = []
    for k, g in enumerate(groups):
        progress(k / len(groups), f"Creando parte {k + 1} de {len(groups)}")
        part = pymupdf.open()
        for i in g:
            part.insert_pdf(doc, from_page=i, to_page=i)
        label = f"pág {g[0] + 1}" if len(g) == 1 else f"págs {g[0] + 1}-{g[-1] + 1}"
        path = os.path.join(folder, f"{stem} ({label}).pdf")
        save_pdf(part, path)
        part.close()
        created.append(path)
    doc.close()
    return {"folder": folder, "files": created}


def extract_pages(src, dst, pages):
    doc = open_pdf(src)
    out = pymupdf.open()
    for i in pages:
        out.insert_pdf(doc, from_page=i, to_page=i)
    save_pdf(out, dst)
    out.close()
    doc.close()


# ---------------------------------------------------------------------------
# Comprimir
# ---------------------------------------------------------------------------

_COMPRESS_LEVELS = {
    "baja": [(200, 85)],
    "media": [(150, 70)],
    "alta": [(110, 55)],
    "objetivo": [(200, 80), (150, 70), (120, 60), (100, 50), (85, 42), (72, 35)],
}


def compress_pdf(src, dst, level="media", target_mb=None, grayscale=False, progress=NULL_PROGRESS):
    original = os.path.getsize(src)
    presets = _COMPRESS_LEVELS["objetivo" if target_mb else level]
    tmpdir = tempfile.mkdtemp(prefix="mkpdf_cmp_")
    best = None
    try:
        for k, (dpi, quality) in enumerate(presets):
            progress(0.1 + 0.8 * k / len(presets), f"Comprimiendo imágenes (calidad {quality})…")
            doc = open_pdf(src)
            try:
                doc.rewrite_images(dpi_threshold=int(dpi * 1.15), dpi_target=dpi, quality=quality,
                                   lossy=True, lossless=True, bitonal=False, color=True, gray=True,
                                   set_to_gray=grayscale)
            except TypeError:
                doc.rewrite_images(dpi_threshold=int(dpi * 1.15), dpi_target=dpi, quality=quality)
            except Exception:
                pass
            try:
                doc.subset_fonts()
            except Exception:
                pass
            tmp = os.path.join(tmpdir, f"p{k}.pdf")
            doc.save(tmp, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True,
                     use_objstms=1)
            doc.close()
            size = os.path.getsize(tmp)
            if best is None or size < best[1]:
                best = (tmp, size)
            if not target_mb or size <= target_mb * 1024 * 1024:
                best = (tmp, size)
                break
        if best[1] >= original:
            shutil.copyfile(src, dst)
            result = {"before": original, "after": original, "improved": False}
        else:
            shutil.copyfile(best[0], dst)
            result = {"before": original, "after": best[1], "improved": True}
        result["reached"] = (not target_mb) or result["after"] <= target_mb * 1024 * 1024
        result["before_h"], result["after_h"] = human_size(result["before"]), human_size(result["after"])
        progress(1.0, "Listo")
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Foliar
# ---------------------------------------------------------------------------

def folio_numbers(n, direction="adelante", start=1):
    if direction == "atras":
        return [start + (n - 1 - i) for i in range(n)]
    return [start + i for i in range(n)]


FOLIO_COLORS = {
    "negro": (0.0, 0.0, 0.0),
    "azul": (0.05, 0.22, 0.62),    # azul de lapicero
    "rojo": (0.80, 0.07, 0.12),    # rojo de lapicero
}


def _color(c):
    if isinstance(c, str):
        if c.startswith("#") and len(c) == 7:
            return tuple(int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        return FOLIO_COLORS.get(c, (0, 0, 0))
    return tuple(c) if c else (0, 0, 0)


def _stamp_folio(page, text, position="sup-der", size=14, box=True, color=(0, 0, 0), margin=22.0):
    """Escribe el folio en la página. Devuelve el recuadro usado (coordenadas de la página)."""
    if page.rotation:
        page.remove_rotation()   # mismo aspecto, coordenadas simples
    col = _color(color)
    font = pymupdf.Font("hebo")
    tw_w = font.text_length(text, fontsize=size)
    bw, bh = tw_w + size * 1.0, size * 1.6
    vr = page.rect
    y0 = margin if position.startswith("sup") else vr.height - margin - bh
    if position.endswith("der"):
        x0 = vr.width - margin - bw
    elif position.endswith("izq"):
        x0 = margin
    else:
        x0 = (vr.width - bw) / 2
    r = pymupdf.Rect(x0, y0, x0 + bw, y0 + bh)
    if box:
        page.draw_rect(r, color=col, fill=(1, 1, 1), width=0.9, overlay=True)
    page.insert_text((x0 + (bw - tw_w) / 2, y0 + bh / 2 + size * 0.36), text, fontsize=size,
                     fontname="hebo", color=col)
    return r


def _folio_text(num, zeros=0, prefix="", total=None):
    n = str(num).zfill(zeros) if zeros else str(num)
    if total is not None:
        t = str(total).zfill(zeros) if zeros else str(total)
        return f"{prefix}{n}/{t}"
    return f"{prefix}{n}"


def _folio_plan(doc, direction, start, skip):
    skip = max(0, min(int(skip), doc.page_count - 1))
    pages = list(range(skip, doc.page_count))
    numbers = folio_numbers(len(pages), direction, start)
    total = start + len(pages) - 1
    return pages, numbers, total


def foliate(src, dst, direction="adelante", start=1, position="sup-der", size=14, box=True,
            zeros=0, prefix="", skip=0, fmt="numero", color="negro", progress=NULL_PROGRESS):
    """Numera las hojas (foliación).

    direction: 'adelante' o 'atras' (de la última a la primera).
    fmt: 'numero' (1, 2, 3…) o 'total' (1/20, 2/20 … 20/20).
    """
    doc = open_pdf(src)
    pages, numbers, total = _folio_plan(doc, direction, start, skip)
    tot = total if fmt == "total" else None
    for k, (i, num) in enumerate(zip(pages, numbers)):
        if k % 10 == 0:
            progress(k / max(1, len(pages)), f"Foliando página {i + 1}")
        _stamp_folio(doc[i], _folio_text(num, zeros, prefix, tot), position, size, box, color)
    save_pdf(doc, dst)
    doc.close()
    return {"pages": len(pages), "first": _folio_text(numbers[0], zeros, "", tot) if numbers else None,
            "last": _folio_text(numbers[-1], zeros, "", tot) if numbers else None}


def folio_preview(src, direction="adelante", start=1, position="sup-der", size=14, box=True,
                  zeros=0, prefix="", skip=0, fmt="numero", color="negro", dpi=42):
    """Primera y última hoja foliadas, para mostrar antes de guardar.

    Devuelve lista de (número de hoja, texto del folio, PNG, recuadro del folio en píxeles).
    """
    doc = open_pdf(src)
    pages, numbers, total = _folio_plan(doc, direction, start, skip)
    tot = total if fmt == "total" else None
    picks = [0, len(pages) - 1] if len(pages) > 1 else [0]
    out = []
    k_px = dpi / 72.0
    for k in picks:
        tmp = pymupdf.open()
        tmp.insert_pdf(doc, from_page=pages[k], to_page=pages[k])
        text = _folio_text(numbers[k], zeros, prefix, tot)
        r = _stamp_folio(tmp[0], text, position, size, box, color)
        pix = tmp[0].get_pixmap(dpi=dpi)
        out.append((pages[k] + 1, text, pix.tobytes("png"), (r.x0 * k_px, r.y0 * k_px, r.x1 * k_px, r.y1 * k_px)))
        tmp.close()
    doc.close()
    return out


# ---------------------------------------------------------------------------
# Igualar tamaño de páginas (A4 con un clic)
# ---------------------------------------------------------------------------

def normalize_size(src, dst, paper="A4", orientation="auto", margin_mm=0, scale_up=True, progress=NULL_PROGRESS):
    doc = open_pdf(src)
    try:
        doc.bake(annots=True, widgets=True)   # conservar anotaciones y firmas visibles
    except Exception:
        pass
    for pg in doc:
        if pg.rotation:
            pg.remove_rotation()
    pw, ph = PAPER.get(paper, PAPER["A4"])
    out = pymupdf.open()
    margin = margin_mm * 72 / 25.4
    changed = 0
    for i, page in enumerate(doc):
        if i % 10 == 0:
            progress(i / doc.page_count, f"Ajustando página {i + 1} de {doc.page_count}")
        vw, vh = page.rect.width, page.rect.height
        landscape = vw > vh and orientation == "auto"
        W, H = (ph, pw) if landscape else (pw, ph)
        newp = out.new_page(width=W, height=H)
        if abs(vw - W) < 2 and abs(vh - H) < 2 and margin == 0:
            newp.show_pdf_page(newp.rect, doc, i)
        else:
            changed += 1
            area = pymupdf.Rect(margin, margin, W - margin, H - margin)
            s = min(area.width / vw, area.height / vh)
            if not scale_up:
                s = min(s, 1.0)
            tw, th = vw * s, vh * s
            target = pymupdf.Rect(area.x0 + (area.width - tw) / 2, area.y0 + (area.height - th) / 2,
                                  area.x0 + (area.width + tw) / 2, area.y0 + (area.height + th) / 2)
            newp.show_pdf_page(target, doc, i)
    save_pdf(out, dst)
    total = out.page_count
    out.close()
    doc.close()
    return {"pages": total, "changed": changed}


# ---------------------------------------------------------------------------
# Imágenes
# ---------------------------------------------------------------------------

def images_to_pdf(images, dst, paper="A4", scanner="no", margin_mm=0, progress=NULL_PROGRESS):
    if not images:
        raise UserError("Agrega al menos una imagen.")
    out = pymupdf.open()
    for k, path in enumerate(images):
        progress(k / len(images), f"Procesando imagen {k + 1} de {len(images)}")
        if scanner in ("color", "bn"):
            img = photoscan.scan_photo(path, scanner)
        else:
            img = photoscan.load_photo(path)
        _image_page(out, img, paper, margin_mm * 72 / 25.4)
    save_pdf(out, dst)
    n = out.page_count
    out.close()
    return {"pages": n}


def pdf_to_images(src, outdir, fmt="jpg", dpi=150, pages=None, progress=NULL_PROGRESS):
    doc = open_pdf(src)
    idx = pages or list(range(doc.page_count))
    stem = os.path.splitext(os.path.basename(src))[0]
    folder = unique_path(os.path.join(outdir, f"{stem} - imágenes"))
    os.makedirs(folder, exist_ok=True)
    files = []
    for k, i in enumerate(idx):
        progress(k / len(idx), f"Página {i + 1} de {doc.page_count}")
        pix = doc[i].get_pixmap(dpi=dpi, alpha=False)
        path = os.path.join(folder, f"{stem} - página {i + 1}.{fmt}")
        if fmt == "jpg":
            pix.save(path, jpg_quality=88)
        else:
            pix.save(path)
        files.append(path)
    doc.close()
    return {"folder": folder, "files": files}


# ---------------------------------------------------------------------------
# Marca de agua
# ---------------------------------------------------------------------------

def watermark(src, dst, text="COPIA", color=(0.6, 0.6, 0.6), opacity=0.25, diagonal=True,
              pages=None, progress=NULL_PROGRESS):
    doc = open_pdf(src)
    font = pymupdf.Font("hebo")
    idx = pages or range(doc.page_count)
    for i in idx:
        page = doc[i]
        if page.rotation:
            page.remove_rotation()
        vr = page.rect
        diag = (vr.width ** 2 + vr.height ** 2) ** 0.5
        target = (diag * 0.62) if diagonal else vr.width * 0.7
        size = max(12, min(160, target / max(1.0, font.text_length(text, fontsize=1))))
        tl = font.text_length(text, fontsize=size)
        center_vis = pymupdf.Point(vr.width / 2, vr.height / 2)
        center = center_vis * page.derotation_matrix
        start = pymupdf.Point(center.x - tl / 2, center.y + size * 0.35)
        tw = pymupdf.TextWriter(page.rect, color=color)
        tw.append(start, text, font=font, fontsize=size)
        angle = (45 if diagonal else 0) + page.rotation
        if angle:
            tw.write_text(page, opacity=opacity, color=color, morph=(center, pymupdf.Matrix(angle)))
        else:
            tw.write_text(page, opacity=opacity, color=color)
    save_pdf(doc, dst)
    doc.close()
    return {}


# ---------------------------------------------------------------------------
# Contraseña
# ---------------------------------------------------------------------------

def protect(src, dst, password, allow_print=True, allow_copy=True):
    if not password:
        raise UserError("Escribe una contraseña.")
    doc = open_pdf(src)
    perm = pymupdf.PDF_PERM_ACCESSIBILITY
    if allow_print:
        perm |= pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
    if allow_copy:
        perm |= pymupdf.PDF_PERM_COPY
    doc.save(dst, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password + "·mk",
             permissions=perm, garbage=3, deflate=True)
    doc.close()


def unprotect(src, dst, password):
    try:
        doc = pymupdf.open(src)
    except Exception:
        raise UserError("No se pudo abrir el archivo.")
    if doc.needs_pass and not doc.authenticate(password or ""):
        doc.close()
        raise UserError("La contraseña no es correcta.")
    doc.save(dst, encryption=pymupdf.PDF_ENCRYPT_NONE, garbage=3, deflate=True)
    doc.close()


def needs_password(path) -> bool:
    try:
        d = pymupdf.open(path)
        r = d.needs_pass
        d.close()
        return bool(r)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Limpiar escaneos
# ---------------------------------------------------------------------------

def is_blank(page, threshold=0.0015) -> bool:
    pix = page.get_pixmap(dpi=50, colorspace=pymupdf.csGRAY)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width)
    h, w = a.shape
    m = int(min(h, w) * 0.05)
    a = a[m:h - m, m:w - m]
    if a.size == 0:
        return True
    norm = ocr.normalize_background(a)
    ink = norm < 140
    ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return ink.mean() < threshold


def clean_scan(src, dst, remove_blank=True, fix_orientation=True, deskew=True, progress=NULL_PROGRESS):
    doc = open_pdf(src)
    out = pymupdf.open()
    removed, rotated, straightened = 0, 0, 0
    n = doc.page_count
    for i, page in enumerate(doc):
        progress(i / n, f"Revisando página {i + 1} de {n}")
        if remove_blank and is_blank(page):
            removed += 1
            continue
        kind = page_kind(page)
        if kind != "escaneada":
            out.insert_pdf(doc, from_page=i, to_page=i)
            continue
        if not fix_orientation and not deskew:
            out.insert_pdf(doc, from_page=i, to_page=i)
            continue
        rgb = ocr.render_rgb(page, 200)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        q = ocr.detect_orientation(gray) if fix_orientation else 0
        angle = 0.0
        if q:
            rgb = ocr.rotate90(rgb, q)
            gray = ocr.rotate90(gray, q)
            rotated += 1
        if deskew:
            angle = ocr.estimate_skew(gray)
            if angle:
                rgb = ocr.rotate_image(rgb, angle)
                straightened += 1
        if not q and not angle:
            out.insert_pdf(doc, from_page=i, to_page=i)
            continue
        vw, vh = page.rect.width, page.rect.height
        if q % 2 == 1:
            vw, vh = vh, vw
        newp = out.new_page(width=vw, height=vh)
        ok, data = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 82])
        newp.insert_image(newp.rect, stream=data.tobytes())
    if out.page_count == 0:
        raise UserError("Todas las páginas parecen estar en blanco.")
    save_pdf(out, dst)
    total = out.page_count
    out.close()
    doc.close()
    return {"pages": total, "removed": removed, "rotated": rotated, "straightened": straightened}


# ---------------------------------------------------------------------------
# Buscar en una carpeta
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def search_folder(folder, query, subfolders=True, progress=NULL_PROGRESS):
    q = _norm(query.strip())
    if not q:
        raise UserError("Escribe la palabra o frase que quieres buscar.")
    pdfs = []
    for root, dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdfs.append(os.path.join(root, f))
        if not subfolders:
            break
    results, no_text = [], []
    for k, path in enumerate(pdfs):
        progress(k / max(1, len(pdfs)), f"Buscando en {os.path.basename(path)}")
        try:
            doc = pymupdf.open(path)
            if doc.needs_pass:
                doc.close()
                continue
        except Exception:
            continue
        has_text = False
        for page in doc:
            text = page.get_text()
            if text.strip():
                has_text = True
            nt = _norm(text)
            pos = nt.find(q)
            if pos >= 0:
                flat = " ".join(text.split())
                nflat = _norm(flat)
                p2 = nflat.find(q)
                a, b = max(0, p2 - 60), min(len(flat), p2 + len(q) + 60)
                snippet = ("…" if a > 0 else "") + flat[a:b] + ("…" if b < len(flat) else "")
                results.append({"file": path, "page": page.number + 1, "snippet": snippet,
                                "count": nt.count(q)})
        if not has_text:
            no_text.append(path)
        doc.close()
    progress(1.0, "Listo")
    return {"results": results, "searched": len(pdfs), "no_text": no_text}


# ---------------------------------------------------------------------------
# Organizar páginas
# ---------------------------------------------------------------------------

def assemble(entries, dst):
    """entries: lista de dict {doc: Document | None, page: int, rotate: int, blank: (w,h) | None}."""
    out = pymupdf.open()
    for e in entries:
        if e.get("blank"):
            w, h = e["blank"]
            out.new_page(width=w, height=h)
            continue
        src = e["doc"]
        out.insert_pdf(src, from_page=e["page"], to_page=e["page"])
        if e.get("rotate"):
            p = out[-1]
            p.set_rotation((p.rotation + e["rotate"]) % 360)
    save_pdf(out, dst)
    n = out.page_count
    out.close()
    return {"pages": n}


def office_to_images(src, outdir, fmt="jpg", dpi=150, progress=NULL_PROGRESS):
    """Word (o Excel) a imágenes: se convierte a PDF con Office y cada página se guarda como imagen."""
    tmpdir = tempfile.mkdtemp(prefix="mkpdf_w2i_")
    try:
        progress(0.05, "Abriendo el documento con Office…")
        stem = os.path.splitext(os.path.basename(src))[0]
        tmp_pdf = os.path.join(tmpdir, stem + ".pdf")
        office_to_pdf(src, tmp_pdf)
        progress(0.4, "Creando imágenes…")
        doc = pymupdf.open(tmp_pdf)
        folder = unique_path(os.path.join(outdir, f"{stem} - imágenes"))
        os.makedirs(folder, exist_ok=True)
        files = []
        n = doc.page_count
        for i, page in enumerate(doc):
            progress(0.4 + 0.6 * i / n, f"Página {i + 1} de {n}")
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            path = os.path.join(folder, f"{stem} - página {i + 1}.{fmt}")
            if fmt == "jpg":
                pix.save(path, jpg_quality=90)
            else:
                pix.save(path)
            files.append(path)
        doc.close()
        return {"folder": folder, "files": files}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
