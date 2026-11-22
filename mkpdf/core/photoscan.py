"""Fotos de documentos tomadas con el celular -> página limpia tipo escáner."""
import cv2
import numpy as np


def load_photo(path: str) -> np.ndarray:
    """Carga una foto respetando la orientación EXIF del celular. Devuelve BGR."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(path)
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        return cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    except Exception:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("No se pudo leer la imagen")
        return img


def _order(pts):
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def find_document(img: np.ndarray):
    """Busca los 4 bordes de la hoja en la foto. Devuelve los puntos o None."""
    h, w = img.shape[:2]
    scale = 1000.0 / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale))) if scale < 1 else img.copy()
    scale = min(scale, 1.0)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    area_img = small.shape[0] * small.shape[1]
    candidates = []
    for lo, hi in ((30, 120), (50, 150), (75, 200)):
        edges = cv2.Canny(gray, lo, hi)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
        contours = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            area = cv2.contourArea(approx)
            if len(approx) == 4 and area > 0.2 * area_img and cv2.isContourConvex(approx):
                candidates.append((area, approx))
    # alternativa: hoja clara sobre fondo oscuro
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    for c in sorted(cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0], key=cv2.contourArea, reverse=True)[:2]:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        area = cv2.contourArea(approx)
        if len(approx) == 4 and area > 0.2 * area_img:
            candidates.append((area, approx))
    if not candidates:
        return None
    area, best = max(candidates, key=lambda x: x[0])
    if area > 0.98 * area_img:
        return None  # la foto ya es solo la hoja
    return _order(best / scale)


def warp_document(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = quad
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 50 or height < 50:
        return img
    dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(quad, dst)
    return cv2.warpPerspective(img, m, (width, height), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def enhance(img: np.ndarray, mode: str = "color") -> np.ndarray:
    """mode: 'color' (fondo blanco, colores vivos) o 'bn' (blanco y negro nítido)."""
    h, w = img.shape[:2]
    k = max(21, (min(h, w) // 25) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    if mode == "bn":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        bg = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        bg = cv2.GaussianBlur(bg, (0, 0), k / 4)
        norm = cv2.divide(gray, bg, scale=255)
        out = cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 12)
        out = cv2.medianBlur(out, 3)
        return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    channels = []
    for ch in cv2.split(img):
        bg = cv2.morphologyEx(ch, cv2.MORPH_CLOSE, kernel)
        bg = cv2.GaussianBlur(bg, (0, 0), k / 4)
        channels.append(cv2.divide(ch, bg, scale=255))
    out = cv2.merge(channels)
    # un poco más de contraste en el texto
    lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.normalize(l, None, 0, 255, cv2.NORM_MINMAX)
    l = np.clip((l.astype(np.float32) - 128) * 1.15 + 140, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def scan_photo(path: str, mode: str = "color", crop: bool = True) -> np.ndarray:
    img = load_photo(path)
    if crop:
        quad = find_document(img)
        if quad is not None:
            img = warp_document(img, quad)
    # limitar tamaño (≈ 200 dpi en A4)
    h, w = img.shape[:2]
    limit = 2400
    if max(h, w) > limit:
        s = limit / max(h, w)
        img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    return enhance(img, mode)
