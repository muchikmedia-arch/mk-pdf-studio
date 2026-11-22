"""Reconocimiento de texto (OCR) con Tesseract integrado en PyMuPDF.

Solo necesita los archivos de idioma (*.traineddata); no requiere instalar Tesseract.
"""
import os
import re

import cv2
import numpy as np
import pymupdf

from ..config import RES_DIR, settings

_WORD_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}[\.,;:]?$")
_VOWEL_RE = re.compile(r"[aeiouáéíóúAEIOUÁÉÍÓÚ]")


def tessdata_dir() -> str:
    candidates = [
        os.environ.get("MKPDF_TESSDATA"),
        os.path.join(RES_DIR, "tessdata"),
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        r"C:\Program Files\Tesseract-OCR\tessdata",
    ]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "spa.traineddata")):
            return c
    raise RuntimeError("No se encontraron los datos de idioma para el OCR (spa.traineddata).")


def ocr_language() -> str:
    lang = settings().get("ocr_lang") or "spa"
    td = tessdata_dir()
    parts = [p for p in lang.split("+") if os.path.isfile(os.path.join(td, p + ".traineddata"))]
    return "+".join(parts) or "spa"


def ocr_dpi() -> int:
    return 300 if settings().get("ocr_quality") != "rapida" else 220


# ----------------------------------------------------------------------------
# Imagen
# ----------------------------------------------------------------------------

def render_gray(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()


def render_rgb(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3).copy()


def load_image_file(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        # formatos raros: usar MuPDF
        pix = pymupdf.Pixmap(path)
        if pix.alpha or pix.n != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
        img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return img


def normalize_background(gray: np.ndarray) -> np.ndarray:
    """Quita fondo gris, sombras y manchas suaves; deja el texto negro sobre blanco."""
    h, w = gray.shape
    k = max(15, (min(h, w) // 40) | 1)
    bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 3)
    norm = cv2.divide(gray, bg, scale=255)
    lo, hi = int(norm.min()), int(norm.max())
    if hi - lo > 40:
        norm = cv2.normalize(norm, None, 0, 255, cv2.NORM_MINMAX)
    return norm


def binarize(gray: np.ndarray) -> np.ndarray:
    """Devuelve máscara de tinta (255 = tinta)."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return bw


def estimate_skew(gray: np.ndarray) -> float:
    """Ángulo de inclinación del texto en grados (método de perfiles de proyección)."""
    h, w = gray.shape
    scale = 900.0 / max(w, 1)
    small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else gray
    bw = binarize(small)
    if bw.mean() < 0.5:  # página casi vacía
        return 0.0
    # quitar líneas largas (tablas) que confunden la medición
    hh, ww = bw.shape
    center = (ww / 2, hh / 2)

    def score(angle):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(bw, m, (ww, hh), flags=cv2.INTER_NEAREST, borderValue=0)
        prof = rot.sum(axis=1, dtype=np.float64)
        return float(np.var(np.diff(prof)))

    best = max(np.arange(-6.0, 6.01, 0.5), key=score)
    fine = max(np.arange(best - 0.5, best + 0.51, 0.1), key=score)
    return float(round(fine, 2)) if abs(fine) >= 0.15 else 0.0


def rotate_image(img: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.01:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = 255 if img.ndim == 2 else (255, 255, 255)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderValue=border)


def rotate90(img: np.ndarray, quarter_turns: int) -> np.ndarray:
    q = quarter_turns % 4
    if q == 0:
        return img
    return np.ascontiguousarray(np.rot90(img, k=-q))  # sentido horario


# ----------------------------------------------------------------------------
# OCR
# ----------------------------------------------------------------------------

def ocr_gray(gray: np.ndarray, dpi: int, lang: str = None):
    """OCR de una imagen en grises. Devuelve (documento, página) con capa de texto."""
    rgb = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    h, w = gray.shape
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, rgb.tobytes(), False)
    pix.set_dpi(dpi, dpi)
    data = pix.pdfocr_tobytes(compress=True, language=lang or ocr_language(), tessdata=tessdata_dir())
    doc = pymupdf.open("pdf", data)
    return doc, doc[0]


_COMMON = set("""de la el en y a los las del que por para con se su al una un es lo como más mas o pero sus le ha
si sin sobre este esta estos estas ya entre cuando todo todos ser son dos también tambien fue había era muy años año
hasta desde está esta mi porque qué que solo sólo han hay vez puede así asi nos ni parte tiene uno donde bien tiempo
mismo ese esa eso ahora cada e otro otra otros otras después despues aunque hace durante siempre día dia tanto tres
según segun menos antes municipal municipalidad distrital provincial regional nacional gestión gestion pública publica
público publico ley artículo articulo resolución resolucion decreto oficina gerencia área area informe proyecto
programa plan presupuesto total servicio servicios señor señora sr sra mediante marco cargo fecha nombre dirección
direccion jefe unidad documento oficio carta acta orden registro the of and to in for is on with by""".split())


def dictionary_hits(text: str) -> int:
    hits = 0
    for w in text.split():
        w = w.strip(".,;:()[]\"'“”¿?¡!").lower()
        if w in _COMMON:
            hits += 1
    return hits


def text_quality(text: str):
    """(palabras plausibles, proporción) para decidir la orientación correcta."""
    words = text.split()
    if not words:
        return 0, 0.0
    good = sum(1 for w in words if _WORD_RE.match(w) and _VOWEL_RE.search(w))
    return good, good / len(words)


def detect_orientation(gray: np.ndarray) -> int:
    """Cuartos de vuelta (0-3, horario) necesarios para dejar el texto derecho."""
    h, w = gray.shape
    scale = 1400.0 / max(h, w)
    small = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else gray
    results = {}
    for q in (0, 2, 1, 3):
        img = rotate90(small, q)
        try:
            doc, page = ocr_gray(img, 150, "spa")
            hits = dictionary_hits(page.get_text())
            doc.close()
        except Exception:
            hits = 0
        results[q] = hits
        # si la orientación normal ya tiene muchas palabras reales, no seguir probando
        if q == 0 and hits >= 12:
            return 0
    best_q = max(results, key=results.get)
    if results[best_q] < 4 or results.get(0, 0) >= results[best_q] * 0.7:
        return 0
    return best_q


_FIXES = [
    (re.compile(r"\bN\s?\.\s?[\?º°o0]\s?(?=\d)"), "N.° "),
    (re.compile(r"\bN\s?[\?º°]\s?(?=\d)"), "N° "),
    (re.compile(r"^N\.\?$"), "N.°"),
    (re.compile(r"\(S\s?[N/]\)?(?=\s|$)"), "(S/)"),
    (re.compile(r"\bS[I1l]\.?\s?(?=\d)"), "S/ "),
    (re.compile(r"^N\?$"), "N°"),
    (re.compile(r"^[!|l]\.(?=\s)"), "I."),
    (re.compile(r"^[!|l]{2}\.(?=\s)"), "II."),
    (re.compile(r"^[!|l]{3}\.(?=\s)"), "III."),
    (re.compile(r"^[!|l]V\.(?=\s)"), "IV."),
    (re.compile(r"\s+([,;:\.])(?=\s|$)"), r"\1"),
    (re.compile(r"(?<=\d)\s?%"), " %"),
]


def fix_text(text: str) -> str:
    """Correcciones conservadoras de errores típicos del OCR en documentos en español."""
    for rx, rep in _FIXES:
        text = rx.sub(rep, text)
    text = text.replace("“ ", "“").replace(" ”", "”")
    return text


def ocr_words(page: pymupdf.Page):
    """Palabras reconocidas: lista de dict con bbox, texto, bloque y línea."""
    words = []
    for x0, y0, x1, y1, txt, b, l, n in page.get_text("words"):
        if txt.strip():
            words.append({"bbox": (x0, y0, x1, y1), "text": txt, "block": b, "line": l, "n": n})
    return words


def prepare_page_image(page: pymupdf.Page, dpi: int, fix_orientation: bool = True):
    """Renderiza, corrige orientación e inclinación y limpia el fondo.

    Devuelve (gris_limpio, color_corregido, angulo, cuartos_de_vuelta).
    """
    rgb = render_rgb(page, dpi)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    q = detect_orientation(gray) if fix_orientation else 0
    if q:
        gray = rotate90(gray, q)
        rgb = rotate90(rgb, q)
    angle = estimate_skew(gray)
    if angle:
        gray = rotate_image(gray, angle)
        rgb = rotate_image(rgb, angle)
    clean = normalize_background(gray)
    return clean, rgb, angle, q
