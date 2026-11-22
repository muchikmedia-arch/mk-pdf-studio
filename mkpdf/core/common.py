"""Utilidades compartidas por todas las herramientas."""
import os
import re

import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)


class Cancelled(Exception):
    """El usuario canceló la tarea."""


class UserError(Exception):
    """Error con un mensaje claro para mostrar al usuario."""


class Progress:
    """Informa el avance (0..1) y permite cancelar."""

    def __init__(self, callback=None, cancel_check=None):
        self.callback = callback
        self.cancel_check = cancel_check

    def __call__(self, fraction: float, message: str = ""):
        self.check()
        if self.callback:
            self.callback(max(0.0, min(1.0, float(fraction))), message)

    def check(self):
        if self.cancel_check and self.cancel_check():
            raise Cancelled()

    def sub(self, start: float, end: float):
        """Progreso parcial dentro de un rango."""
        parent = self

        class _Sub(Progress):
            def __call__(self, fraction, message=""):
                parent(start + (end - start) * max(0.0, min(1.0, fraction)), message)

            def check(self):
                parent.check()

        return _Sub()


NULL_PROGRESS = Progress()

PDF_EXT = (".pdf",)
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".gif")
WORD_EXT = (".doc", ".docx", ".odt", ".rtf")
EXCEL_EXT = (".xls", ".xlsx", ".ods", ".csv")


def ext_of(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"


def output_path(src: str, suffix: str, ext: str, outdir: str = None) -> str:
    """Ruta de salida al lado del original, sin sobrescribir nada."""
    folder = outdir or os.path.dirname(os.path.abspath(src))
    stem = os.path.splitext(os.path.basename(src))[0]
    name = f"{stem} - {suffix}{ext}" if suffix else f"{stem}{ext}"
    return unique_path(os.path.join(folder, name))


def open_pdf(path: str, password: str = None) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except Exception:
        raise UserError("No se pudo abrir el archivo. Puede estar dañado o no ser un PDF.")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise UserError("Este PDF tiene contraseña. Primero quítala en Herramientas > Contraseña.")
    if not doc.is_pdf:
        # imágenes u otros formatos abiertos por MuPDF: convertir a PDF
        pdf_bytes = doc.convert_to_pdf()
        doc.close()
        doc = pymupdf.open("pdf", pdf_bytes)
    return doc


def is_signed(path_or_doc) -> bool:
    """True si el PDF tiene firma digital (ReFirma, Firma Perú, etc.)."""
    try:
        doc = path_or_doc if isinstance(path_or_doc, pymupdf.Document) else pymupdf.open(path_or_doc)
        flags = doc.get_sigflags()
        if flags and flags > 0:
            return True
        for page in doc:
            for w in page.widgets() or []:
                if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE and w.field_value:
                    return True
    except Exception:
        return False
    return False


def page_kind(page: pymupdf.Page) -> str:
    """Clasifica una página: 'digital', 'escaneada' o 'vacia'."""
    area = abs(page.rect) or 1
    visible_chars = 0
    try:
        for span in page.get_texttrace():
            if span.get("type", 0) != 3 and span.get("opacity", 1) > 0:
                visible_chars += len(span.get("chars", ()))
    except Exception:
        visible_chars = len(page.get_text("text").strip())
    img_cover = 0.0
    try:
        for info in page.get_image_info():
            r = pymupdf.Rect(info["bbox"]) & page.rect
            if not r.is_empty:
                img_cover += abs(r)
    except Exception:
        pass
    img_ratio = img_cover / area
    if visible_chars >= 40:
        return "digital"
    if img_ratio >= 0.35:
        return "escaneada"
    # Texto convertido en curvas (sin letras reales): tratar como escaneado
    try:
        n_paths = len(page.get_drawings())
    except Exception:
        n_paths = 0
    if n_paths > 150:
        return "escaneada"
    if visible_chars > 0:
        return "digital"
    return "vacia" if img_ratio < 0.02 and n_paths < 5 else "escaneada"


def parse_ranges(text: str, page_count: int):
    """'1-3, 5, 8-' -> lista de grupos de índices (base 0)."""
    groups = []
    if not text or not text.strip():
        return groups
    for part in re.split(r"[;,]", text):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*[-–a]\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else page_count
        elif part.isdigit():
            a = b = int(part)
        else:
            raise UserError(f"No entiendo el rango «{part}». Usa por ejemplo: 1-3, 5, 8-10")
        if a < 1 or b > page_count or a > b:
            raise UserError(f"El rango «{part}» no existe. El documento tiene {page_count} páginas.")
        groups.append(list(range(a - 1, b)))
    return groups


def pages_from_ranges(text: str, page_count: int):
    if not text or not text.strip():
        return list(range(page_count))
    seen, out = set(), []
    for g in parse_ranges(text, page_count):
        for i in g:
            if i not in seen:
                seen.add(i)
                out.append(i)
    return out


def human_size(nbytes: int) -> str:
    if nbytes < 1024:
        return f"{nbytes} bytes"
    if nbytes < 1024 * 1024:
        return f"{nbytes / 1024:.0f} KB"
    return f"{nbytes / (1024 * 1024):.1f} MB"


def save_pdf(doc: pymupdf.Document, path: str, compress: bool = True):
    doc.save(path, garbage=3 if compress else 0, deflate=compress, deflate_images=compress,
             deflate_fonts=compress, clean=False)
