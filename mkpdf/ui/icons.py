"""Íconos de línea dibujados para el programa (SVG propio, se colorean según el tema)."""
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_S = 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
_DOC = 'M6 2.8h8.2L19 7.6V20a1.2 1.2 0 0 1-1.2 1.2H6A1.2 1.2 0 0 1 4.8 20V4A1.2 1.2 0 0 1 6 2.8z M14 2.8V7.8h5'

PATHS = {
    "word": f'<path d="{_DOC}"/><path d="M7.6 11l1.3 6 1.6-4.6 1.6 4.6 1.3-6"/>',
    "excel": f'<path d="{_DOC}"/><path d="M7.5 11h8 M7.5 14h8 M7.5 17h8 M10.5 11v6"/>',
    "ppt": f'<path d="{_DOC}"/><path d="M8.5 17.5v-6.5h2.8a2.1 2.1 0 0 1 0 4.2H8.5"/>',
    "wordimg": '<rect x="3" y="3" width="11" height="14" rx="1.5"/><path d="M5.6 7l.9 4 1.1-3 1.1 3 .9-4"/><rect x="11" y="11" width="10" height="10" rx="1.5"/><path d="M11 19l3-3 2 2 2-2.5 3 3"/>',
    "pdfimg": '<rect x="3" y="3" width="11" height="14" rx="1.5"/><path d="M5.5 7.5h6 M5.5 10h6 M5.5 12.5h3.5"/><rect x="11" y="11" width="10" height="10" rx="1.5"/><path d="M11 19l3-3 2 2 2-2.5 3 3"/>',
    "editpdf": f'<path d="{_DOC}"/><path d="M8 18h2.2l6-6a1.4 1.4 0 0 0-2-2l-6 6z"/>',
    "ocr": '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8 M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8 M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16 M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><path d="M8 9h8 M8 12h8 M8 15h5"/>',
    "imagetext": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8 9h8 M12 9v8"/>',
    "pages": '<rect x="3.5" y="3.5" width="7" height="8" rx="1"/><rect x="13.5" y="3.5" width="7" height="8" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><rect x="13.5" y="13.5" width="7" height="7" rx="1"/>',
    "tools": '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.2L3.6 17.2a1.6 1.6 0 0 0 2.3 2.3l5.7-5.7a4 4 0 0 0 5.2-5.4l-2.6 2.6-2.2-.4-.4-2.2z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6 M12 7.5v.2"/>',
    "merge": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="9" rx="1"/><path d="M6.5 12v3.5h11V12 M12 15.5V21 M9.5 18.5L12 21l2.5-2.5"/>',
    "split": '<circle cx="6" cy="6" r="2.6"/><circle cx="6" cy="18" r="2.6"/><path d="M20 4L8.1 15.9 M14.5 14.5L20 20 M8.1 8.1L12 12"/>',
    "compress": '<path d="M4 14h6v6 M20 10h-6V4 M14 10l7-7 M3 21l7-7"/>',
    "folio": f'<path d="{_DOC}"/><rect x="11.3" y="10" width="6" height="4.6" rx=".8"/><path d="M7.5 17h9"/>',
    "a4": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 8.5L7.5 7 M7.5 7h3 M7.5 7v3 M15 15.5l1.5 1.5 M16.5 17h-3 M16.5 17v-3"/>',
    "camera": '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2.3l1.5-2.2h5.4L16.2 7h2.3A1.5 1.5 0 0 1 20 8.5v9A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5z"/><circle cx="12" cy="13" r="3.4"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.7"/><path d="M21 16l-5-5L5 20"/>',
    "drop": '<path d="M12 3.2s6 6.6 6 10.8a6 6 0 0 1-12 0c0-4.2 6-10.8 6-10.8z"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    "clean": '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z M18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z M5.5 15.5l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
    "back": '<path d="M19 12H5 M11 18l-6-6 6-6"/>',
    "fwd": '<path d="M5 12h14 M13 6l6 6-6 6"/>',
    "cursor": '<path d="M5.5 3.5l13 7.5-5.8 1.5-2.7 5.8z"/>',
    "type": '<path d="M5 7V4.5h14V7 M12 4.5V19.5 M9 19.5h6"/>',
    "fixtext": '<path d="M3.5 7V5h10v2 M8.5 5v11 M6.5 16h4"/><path d="M13.5 20.5h2l5.3-5.3a1.4 1.4 0 0 0-2-2l-5.3 5.3z"/>',
    "marker": '<path d="M15 4l5 5-8.5 8.5H7v-4.5z M12.5 6.5l5 5 M3 21h18"/>',
    "underline": '<path d="M7 4v7a5 5 0 0 0 10 0V4 M5 20h14"/>',
    "strike": '<path d="M4 12h16 M16.5 7.6C15.8 6 14.2 5 12 5 9.4 5 7.5 6.3 7.5 8.3c0 1.4.9 2.3 2.6 2.9 M7.5 16.4C8.2 18 9.8 19 12 19c2.7 0 4.5-1.3 4.5-3.3 0-.6-.1-1.1-.4-1.5"/>',
    "note": '<path d="M4 4h16v12h-6.5L9 20v-4H4z M8 8.5h8 M8 11.8h5"/>',
    "eraser": '<path d="M8 20h12 M4.6 15.4l9.2-9.2a1.5 1.5 0 0 1 2.1 0l3 3a1.5 1.5 0 0 1 0 2.1L12 18.2H8.2z M9 11l4.9 4.9"/>',
    "signature": '<path d="M3 16.5c2.5-.5 3.5-8.5 6-8.5 1.8 0-.3 7.5 1.8 7.5 1.6 0 2-4 3.8-4 1.5 0 .9 3 2.8 3 1.3 0 2.2-1 3.6-1 M3 20.5h18"/>',
    "stamp": '<path d="M9.5 3h5l-.8 6.5h3.3a2 2 0 0 1 2 2v2.5H5v-2.5a2 2 0 0 1 2-2h3.3z M5 17h14 M7 20.5h10"/>',
    "pen": '<path d="M4 20l1.1-4.4L15.6 5.1a2.1 2.1 0 0 1 3 3L8.4 18.9z M13.6 7.1l3 3"/>',
    "square": '<rect x="4" y="5" width="16" height="14" rx="1.5"/>',
    "form": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M6.5 9h5 M6.5 14h11"/>',
    "fit": '<path d="M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5"/>',
    "prev": '<path d="M15 5l-7 7 7 7"/>',
    "next": '<path d="M9 5l7 7-7 7"/>',
    "rotl": '<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6 M3 3.5V8h4.5"/>',
    "rotr": '<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6 M21 3.5V8h-4.5"/>',
    "trash": '<path d="M4 7h16 M9.5 7V4.5h5V7 M6.5 7l1 13h9l1-13 M10 11v5.5 M14 11v5.5"/>',
    "plus": '<path d="M12 5v14 M5 12h14"/>',
    "blank": '<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M12 9v6 M9 12h6"/>',
    "extract": f'<path d="{_DOC}"/><path d="M12 10v7 M9 14l3 3 3-3"/>',
    "undo": '<path d="M9 14L4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "save": '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z M8 3v5h7V3 M8 21v-6h8v6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "file": f'<path d="{_DOC}"/>',
    "check": '<path d="M4.5 12.5l5 5L19.5 7"/>',
    "warn": '<path d="M12 3.5L22 20H2z M12 10v4.5 M12 17.3v.2"/>',
    "close": '<path d="M6 6l12 12 M18 6L6 18"/>',
    "exit": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4 M10 16l-4-4 4-4 M6 12h10"/>',
    "share": '<circle cx="18" cy="5.5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="18.5" r="2.6"/><path d="M8.3 10.8l7.4-4 M8.3 13.2l7.4 4"/>',
    "magic": '<path d="M4 20L15 9 M13.5 7.5l3 3 M18 3v3 M16.5 4.5h3 M20.5 9v2 M19.5 10h2 M9 3.5v2 M8 4.5h2"/>',
    "whatsapp": '<path d="M4 20l1.2-4.2A8 8 0 1 1 8.4 19z"/><path d="M9 8.5c0 3.2 2.8 6.5 6.4 6.5l1-1.6-2-1.1-1 1c-1.4-.6-2.4-1.7-3-3l1-1-1-2z"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5L12 13l8.5-6.5"/>',
    "chat": '<path d="M12 3.5c4.7 0 8.5 3.3 8.5 7.5S16.7 18.5 12 18.5c-1 0-2-.1-2.9-.4L5 20l1-3.4A7.2 7.2 0 0 1 3.5 11c0-4.2 3.8-7.5 8.5-7.5z M7.5 12.5l3-3 2.5 2 3.5-3"/>',
    "up": '<path d="M12 19V5 M6 11l6-6 6 6"/>',
    "down": '<path d="M12 5v14 M6 13l6 6 6-6"/>',
    "upload": '<path d="M12 16V4 M7 9l5-5 5 5 M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "open": '<path d="M14 4h6v6 M20 4l-9 9 M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
    "zoomin": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21 M10.5 8v5 M8 10.5h5"/>',
    "zoomout": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21 M8 10.5h5"/>',
    "edit": '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3z M14.5 7.5l2 2"/>',
}


def svg(name: str, color: str) -> str:
    body = PATHS.get(name, PATHS["file"])
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {_S}>{body}</svg>'.replace("currentColor", color)


def pixmap(name: str, color: str, size: int, ratio: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color).encode("utf-8")))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int = 24) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size))
    return ic


# ---------------------------------------------------------------------------
# Logo del programa
# ---------------------------------------------------------------------------

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs>
 <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#2E6BF0"/><stop offset="1" stop-color="#1A3C9C"/>
 </linearGradient>
</defs>
<rect x="8" y="8" width="240" height="240" rx="56" fill="url(#g)"/>
<path d="M78 46h70l42 42v116a10 10 0 0 1-10 10H78a10 10 0 0 1-10-10V56a10 10 0 0 1 10-10z" fill="#FFFFFF"/>
<path d="M148 46v32a10 10 0 0 0 10 10h32z" fill="#C9D8FB"/>
<rect x="52" y="150" width="92" height="44" rx="10" fill="#E53935"/>
<text x="98" y="181" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="700" fill="#FFFFFF" text-anchor="middle">PDF</text>
<text x="128" y="134" font-family="Arial, Helvetica, sans-serif" font-size="58" font-weight="800" fill="#1A3C9C" text-anchor="middle">MK</text>
</svg>"""


def logo_pixmap(size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(LOGO_SVG.encode("utf-8")))
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    renderer.render(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def app_icon() -> QIcon:
    import os
    from ..config import RES_DIR
    ico = os.path.join(RES_DIR, "app.ico")
    if os.path.isfile(ico):
        ic = QIcon(ico)
        if not ic.isNull():
            return ic
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s))
    return ic
