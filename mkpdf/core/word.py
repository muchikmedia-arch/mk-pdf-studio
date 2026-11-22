"""PDF (digital o escaneado) a Word editable, conservando márgenes y posiciones."""
import logging
import os
import re
import tempfile

import pymupdf

from . import p2d_tuning, scanlayout
from .common import NULL_PROGRESS, UserError, open_pdf, page_kind
from ..config import settings

_PAGE_RE = re.compile(r"\((\d+)/(\d+)\)")

_FONT_ALIASES = {
    "liberation sans": "Arial", "liberationsans": "Arial", "arialmt": "Arial", "helvetica": "Arial",
    "liberation serif": "Times New Roman", "liberationserif": "Times New Roman",
    "timesnewromanpsmt": "Times New Roman", "times-roman": "Times New Roman",
    "carlito": "Calibri", "dejavu sans": "Arial",
}


class _LogProgress(logging.Handler):
    """Convierte los mensajes del motor de conversión en avance (0..1)."""

    def __init__(self, progress, start, end):
        super().__init__(logging.INFO)
        self.progress, self.start, self.end = progress, start, end
        self.phase = 0  # 0: análisis, 1: creación
        self.last = (0, 0)

    def emit(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return
        m = _PAGE_RE.search(msg)
        if not m:
            if "Creating pages" in msg:
                self.phase = 1
            return
        i, n = int(m.group(1)), int(m.group(2))
        frac = (i / max(n, 1)) * 0.6 if self.phase == 0 else 0.6 + 0.4 * (i / max(n, 1))
        self.progress(self.start + (self.end - self.start) * frac,
                      f"Armando el documento Word: página {i} de {n}")


def _run_pdf2docx(pdf_path, docx_path, progress, start, end, pages=None):
    from pdf2docx import Converter
    p2d_tuning.apply()
    handler = _LogProgress(progress, start, end)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        cv = Converter(pdf_path)
        try:
            cv.convert(docx_path, pages=pages, multi_processing=False,
                       ignore_page_error=True, delete_end_line_hyphen=False)
        finally:
            cv.close()
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _fix_fonts(docx_path, scanned_font=None):
    """Nombres de fuentes compatibles -> nombres de Windows (Arial, Times New Roman, Calibri)."""
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except Exception:
        return
    d = Document(docx_path)

    def norm(name):
        if not name:
            return name
        key = name.lower().replace("-", " ").strip()
        key = re.sub(r"\s+(regular|bold|italic|bolditalic|mt)$", "", key)
        return _FONT_ALIASES.get(key, _FONT_ALIASES.get(key.replace(" ", ""), name))

    def fix_run(run):
        rpr = run._element.rPr
        if rpr is None or rpr.rFonts is None:
            return
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            val = rpr.rFonts.get(qn(attr))
            if val:
                rpr.rFonts.set(qn(attr), norm(val))

    def walk(paragraphs, tables):
        for p in paragraphs:
            for r in p.runs:
                fix_run(r)
        for t in tables:
            for row in t.rows:
                for cell in row.cells:
                    walk(cell.paragraphs, cell.tables)

    walk(d.paragraphs, d.tables)
    for s in d.sections:
        for part in (s.header, s.footer):
            try:
                walk(part.paragraphs, part.tables)
            except Exception:
                pass
    d.save(docx_path)


def analyze_document(src, pages=None, progress=NULL_PROGRESS):
    doc = open_pdf(src)
    idx = pages if pages else list(range(len(doc)))
    kinds = {i: page_kind(doc[i]) for i in idx}
    return doc, idx, kinds


def pdf_to_word(src: str, dst: str, pages=None, force_ocr: bool = False, progress=NULL_PROGRESS) -> dict:
    """Convierte un PDF a .docx. Devuelve un resumen."""
    progress(0.01, "Revisando el documento…")
    doc, idx, kinds = analyze_document(src, pages)
    if not idx:
        raise UserError("El documento no tiene páginas.")
    scanned = [i for i in idx if force_ocr or kinds[i] == "escaneada"]
    font = settings().get("scan_font") or "Arial"
    summary = {"pages": len(idx), "scanned": len(scanned), "digital": len(idx) - len(scanned)}

    if not scanned:
        doc.close()
        _run_pdf2docx(src, dst, progress, 0.05, 0.97, pages=idx if pages else None)
        _fix_fonts(dst)
        progress(1.0, "Listo")
        return summary

    # Documento intermedio: páginas digitales tal cual + páginas escaneadas reconstruidas
    n = len(idx)
    ocr_share = 0.75
    analyzed = {}
    for k, i in enumerate(idx):
        if i in scanned:
            sub = progress.sub(0.02 + ocr_share * k / n, 0.02 + ocr_share * (k + 1) / n)
            progress(0.02 + ocr_share * k / n, f"Reconociendo texto (OCR): página {k + 1} de {n}")
            analyzed[i] = scanlayout.analyze_page(doc[i], progress=sub)
    scanlayout.fix_roman_headings([analyzed[i] for i in idx if i in analyzed])
    work = pymupdf.open()
    for i in idx:
        if i in analyzed:
            scanlayout.build_page(work, analyzed[i], font)
        else:
            work.insert_pdf(doc, from_page=i, to_page=i)
    doc.close()
    tmpdir = tempfile.mkdtemp(prefix="mkpdf_")
    tmp_pdf = os.path.join(tmpdir, "intermedio.pdf")
    work.save(tmp_pdf, garbage=3, deflate=True)
    work.close()
    try:
        _run_pdf2docx(tmp_pdf, dst, progress, 0.78, 0.97)
        _fix_fonts(dst, font)
    finally:
        try:
            os.remove(tmp_pdf)
            os.rmdir(tmpdir)
        except Exception:
            pass
    progress(1.0, "Listo")
    return summary


def image_to_word(src: str, dst: str, progress=NULL_PROGRESS) -> dict:
    """Foto o imagen con texto -> Word editable (con OCR)."""
    from .searchable import image_to_pdf_for_ocr
    doc = image_to_pdf_for_ocr(src)
    tmpdir = tempfile.mkdtemp(prefix="mkpdf_")
    tmp_pdf = os.path.join(tmpdir, "imagen.pdf")
    doc.save(tmp_pdf)
    doc.close()
    try:
        return pdf_to_word(tmp_pdf, dst, force_ocr=True, progress=progress)
    finally:
        try:
            os.remove(tmp_pdf)
            os.rmdir(tmpdir)
        except Exception:
            pass
