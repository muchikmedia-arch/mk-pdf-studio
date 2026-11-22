"""Quitar el fondo a firmas y sellos escaneados o fotografiados.

Cómo funciona (pensado para no recortar partes de la firma):
1. Se calcula el color del papel en cada zona (corrige sombras y luz desigual del celular).
2. Cada píxel recibe una "fuerza de tinta" comparándolo con el papel que tiene debajo.
3. La transparencia es gradual (bordes suaves) y se conservan los trazos débiles que estén
   conectados a un trazo fuerte; se descartan solo las manchitas débiles y sueltas del papel.
4. Se recupera el color real de la tinta (sin el halo blanco del papel).
"""
import cv2
import numpy as np

INK_COLORS = {
    "original": None,
    "azul": (24, 52, 150),        # azul de lapicero
    "negro": (20, 20, 24),
    "rojo": (196, 18, 36),
    "morado": (88, 40, 140),      # tinta de sello violeta
    "azul_sello": (30, 70, 185),
}


def load_rgb(path: str) -> np.ndarray:
    from PIL import Image, ImageOps
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    return np.asarray(im.convert("RGB")).copy()


def _background(rgb: np.ndarray) -> np.ndarray:
    """Color del papel en cada punto (float32), sin la tinta."""
    h, w = rgb.shape[:2]
    scale = min(1.0, 600.0 / max(h, w))
    small = cv2.resize(rgb, (max(8, int(w * scale)), max(8, int(h * scale))), interpolation=cv2.INTER_AREA)
    small = small.astype(np.float32)
    lum = small.mean(axis=2)
    paper = np.percentile(lum, 85)
    # 1) quitar trazos finos con un cierre morfológico (máximo local) y suavizar
    k = max(9, (min(small.shape[:2]) // 14) | 1)
    closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    # 2) promedio ponderado solo con los puntos que parecen papel (evita tomar manchas grandes de tinta)
    mask = (lum >= paper - max(25.0, 0.18 * paper)).astype(np.float32)
    sigma = max(small.shape[:2]) / 10.0
    num = cv2.GaussianBlur(closed * mask[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(mask, (0, 0), sigma)[..., None]
    global_paper = np.array([np.percentile(small[..., c][mask > 0], 60) if mask.any() else 255.0
                             for c in range(3)], dtype=np.float32)
    bg = np.where(den > 0.05, num / np.maximum(den, 1e-3), global_paper)
    bg = cv2.GaussianBlur(bg, (0, 0), max(1.0, sigma / 4))
    bg = np.maximum(bg, 30.0)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)


def remove_background(rgb: np.ndarray, sensitivity: int = 50, color: str = "original",
                      intensity: int = 100, crop: bool = True) -> np.ndarray:
    """Devuelve una imagen RGBA (uint8) con fondo transparente.

    sensitivity: 0-100 (más alto = conserva trazos más suaves).
    color: 'original' o una clave de INK_COLORS.
    intensity: 50-200 (% de intensidad del color de la tinta).
    """
    img = rgb.astype(np.float32)
    bg = _background(rgb)
    ratio = np.clip(img / bg, 0.0, 1.0)
    strength = 1.0 - ratio.min(axis=2)          # fuerza de tinta 0..1 (sirve también para tintas de color)
    strength = cv2.GaussianBlur(strength, (3, 3), 0.6)

    # Ruido del papel: medido donde casi no hay tinta
    paper_px = strength[strength < np.percentile(strength, 60)]
    noise = float(np.std(paper_px)) if paper_px.size else 0.02
    base = float(np.median(paper_px)) if paper_px.size else 0.0
    ink_px = strength[strength > base + 6 * noise + 0.05]
    strong_level = float(np.percentile(ink_px, 75)) if ink_px.size > 50 else 0.5
    strong_level = float(np.clip(strong_level, 0.18, 0.9))

    s = float(np.clip(sensitivity, 0, 100)) / 100.0
    low = base + noise * (5.5 - 3.5 * s) + 0.035 * (1.3 - s)
    low = float(np.clip(low, 0.02, strong_level * 0.6))
    full = max(low + 0.06, strong_level * (0.85 - 0.25 * s))
    alpha = np.clip((strength - low) / (full - low), 0.0, 1.0)

    # Limpieza: se descartan solo las manchitas sueltas que son a la vez pequeñas y débiles.
    # Una letra o trazo tenue se conserva si tiene tamaño de trazo o algo de tinta clara.
    weak = (alpha > 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(weak, connectivity=8)
    if n > 1:
        peak = np.zeros(n, dtype=np.float32)
        np.maximum.at(peak, labels.ravel(), strength.ravel())
        area = stats[:, cv2.CC_STAT_AREA]
        mid = low + 0.45 * (full - low)
        min_area = max(12, int(0.000015 * strength.size * (1.2 - s)))
        keep = (peak >= mid) | ((area >= min_area) & (peak >= low + 0.25 * (full - low)))
        keep[0] = False
        alpha = alpha * keep[labels]

    # Color real de la tinta: I = a*C + (1-a)*Papel  ->  C = (I - (1-a)*Papel) / a
    a3 = np.maximum(alpha, 1e-3)[..., None]
    ink = (img - (1.0 - alpha[..., None]) * bg) / a3
    ink = np.clip(ink, 0, 255)
    solid = alpha > 0.6
    if solid.any():
        ref = np.median(ink[solid], axis=0)
    else:
        ref = np.array([30.0, 30.0, 30.0])
    t = np.clip(alpha / 0.45, 0, 1)[..., None]
    ink = ink * t + ref * (1 - t)

    k = float(np.clip(intensity, 30, 250)) / 100.0
    target = INK_COLORS.get(color)
    if target is not None:
        # recolorear conservando un poco del sombreado original
        lum = ink.mean(axis=2, keepdims=True) / 255.0
        tgt = np.array(target, dtype=np.float32)
        ink = np.clip(tgt * (0.75 + 0.5 * lum), 0, 255)
        alpha = 1.0 - (1.0 - alpha) ** k
        if k > 1:
            ink = ink * (1.0 - 0.18 * (k - 1))
    else:
        hsv = cv2.cvtColor((ink / 255.0).astype(np.float32), cv2.COLOR_RGB2HSV)
        hsv[..., 1] = np.clip(hsv[..., 1] * k, 0, 1)
        hsv[..., 2] = np.clip(hsv[..., 2] ** k, 0, 1)
        ink = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB) * 255.0
        if k > 1:
            alpha = 1.0 - (1.0 - alpha) ** (1 + (k - 1) * 0.6)
    out = np.dstack([np.clip(ink, 0, 255), np.clip(alpha * 255.0, 0, 255)]).astype(np.uint8)

    if crop:
        ys, xs = np.where(out[..., 3] > 10)
        if len(xs):
            pad = max(4, int(0.02 * max(out.shape[:2])))
            y0, y1 = max(0, ys.min() - pad), min(out.shape[0], ys.max() + pad + 1)
            x0, x1 = max(0, xs.min() - pad), min(out.shape[1], xs.max() + pad + 1)
            out = out[y0:y1, x0:x1]
    return out


def process_file(path: str, max_side: int = 2600, **kw) -> np.ndarray:
    rgb = load_rgb(path)
    h, w = rgb.shape[:2]
    if max(h, w) > max_side:
        f = max_side / max(h, w)
        rgb = cv2.resize(rgb, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA)
    return remove_background(rgb, **kw)


def save_png(rgba: np.ndarray, path: str, dpi: int = 300):
    from PIL import Image
    Image.fromarray(rgba, "RGBA").save(path, dpi=(dpi, dpi), optimize=True)
