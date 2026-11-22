"""Temas de color y tamaño de letra del programa."""
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

THEMES = {
    "claro": {
        "name": "Claro",
        "bg": "#F4F6FA", "surface": "#FFFFFF", "surface2": "#EEF2F8", "border": "#DCE3EE",
        "text": "#1C2333", "muted": "#5D6779", "accent": "#2155D6", "accent_hover": "#1B47B5",
        "accent_text": "#FFFFFF", "accent_soft": "#E6EDFC", "ok": "#1E8E4E", "ok_soft": "#E5F5EC",
        "warn": "#8A5A00", "warn_soft": "#FFF4D6", "danger": "#C62828", "danger_soft": "#FDECEC",
        "header": "#FFFFFF",
    },
    "oscuro": {
        "name": "Oscuro",
        "bg": "#16181D", "surface": "#1F2229", "surface2": "#272B34", "border": "#343A46",
        "text": "#E8EBF1", "muted": "#9AA3B2", "accent": "#5B8DEF", "accent_hover": "#77A1F3",
        "accent_text": "#0E1220", "accent_soft": "#26324A", "ok": "#4CC27D", "ok_soft": "#1E3328",
        "warn": "#F2C14E", "warn_soft": "#3A321C", "danger": "#F07070", "danger_soft": "#3A2224",
        "header": "#1F2229",
    },
    "verde": {
        "name": "Verde",
        "bg": "#F3F7F4", "surface": "#FFFFFF", "surface2": "#EAF2EC", "border": "#D5E3D9",
        "text": "#1B2A22", "muted": "#58695F", "accent": "#1F7A4D", "accent_hover": "#18643F",
        "accent_text": "#FFFFFF", "accent_soft": "#E2F1E8", "ok": "#1F7A4D", "ok_soft": "#E2F1E8",
        "warn": "#8A5A00", "warn_soft": "#FFF4D6", "danger": "#C62828", "danger_soft": "#FDECEC",
        "header": "#FFFFFF",
    },
    "contraste": {
        "name": "Alto contraste",
        "bg": "#FFFFFF", "surface": "#FFFFFF", "surface2": "#F2F2F2", "border": "#000000",
        "text": "#000000", "muted": "#222222", "accent": "#0033A0", "accent_hover": "#00237A",
        "accent_text": "#FFFFFF", "accent_soft": "#DDE6FF", "ok": "#006B2E", "ok_soft": "#DFF5E6",
        "warn": "#5C3B00", "warn_soft": "#FFE9A8", "danger": "#A00000", "danger_soft": "#FFE0E0",
        "header": "#FFFFFF",
    },
}

_current = {"theme": "claro", "scale": 100}
_ASSETS = ""


def _write_assets(c):
    """Pequeñas imágenes (visto, flechas) con los colores del tema para la hoja de estilos."""
    global _ASSETS
    import os
    from ..config import user_data_dir
    folder = os.path.join(user_data_dir(), "ui")
    os.makedirs(folder, exist_ok=True)
    files = {
        "check.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="{c["accent_text"]}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "up.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 15l7-7 7 7" fill="none" stroke="{c["text"]}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "down.svg": f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M5 9l7 7 7-7" fill="none" stroke="{c["text"]}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    }
    for name, data in files.items():
        try:
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write(data)
        except Exception:
            pass
    _ASSETS = folder.replace("\\", "/")


def colors():
    return THEMES.get(_current["theme"], THEMES["claro"])


def px(base: float) -> int:
    return max(8, int(round(base * _current["scale"] / 100.0)))


def build_qss(c) -> str:
    f = px(15)
    return f"""
* {{ font-size: {f}px; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QWidget#Page, QWidget#Tab, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c['bg']}; }}
QWidget#Header {{ background: {c['header']}; border-bottom: 1px solid {c['border']}; }}
QWidget#Footer {{ background: {c['bg']}; border-top: 1px solid {c['border']}; }}
QLabel {{ background: transparent; }}
QLabel#AppTitle {{ font-size: {px(21)}px; font-weight: 700; }}
QLabel#AppSubtitle, QLabel#Muted {{ color: {c['muted']}; }}
QLabel#FooterText {{ color: {c['muted']}; font-size: {px(13)}px; border: none; }}
QLabel#PageTitle {{ font-size: {px(24)}px; font-weight: 700; }}
QLabel#SectionTitle {{ font-size: {px(17)}px; font-weight: 700; }}
QLabel#StepNumber {{ background: {c['accent']}; color: {c['accent_text']}; border-radius: {px(14)}px;
    min-width: {px(28)}px; max-width: {px(28)}px; min-height: {px(28)}px; max-height: {px(28)}px;
    font-weight: 700; qproperty-alignment: AlignCenter; }}
QLabel#Big {{ font-size: {px(19)}px; font-weight: 600; }}

/* Pestañas principales */
QPushButton#TabButton {{ background: transparent; border: none; border-bottom: 3px solid transparent;
    padding: {px(12)}px {px(14)}px; font-size: {px(16)}px; font-weight: 600; color: {c['muted']}; border-radius: 0; }}
QPushButton#TabButton:hover {{ color: {c['text']}; background: {c['surface2']}; }}
QPushButton#TabButton:checked {{ color: {c['accent']}; border-bottom: 3px solid {c['accent']}; }}

/* Botones */
QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px;
    padding: {px(9)}px {px(16)}px; }}
QPushButton:hover {{ background: {c['surface2']}; }}
QPushButton:pressed {{ background: {c['accent_soft']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['surface2']}; border-color: {c['border']}; }}
QPushButton#Primary {{ background: {c['accent']}; color: {c['accent_text']}; border: none; font-weight: 700;
    padding: {px(13)}px {px(28)}px; font-size: {px(17)}px; }}
QPushButton#Primary:hover {{ background: {c['accent_hover']}; }}
QPushButton#Primary:disabled {{ background: {c['border']}; color: {c['muted']}; }}
QPushButton#Flat {{ background: transparent; border: none; color: {c['accent']}; font-weight: 600; padding: {px(6)}px {px(8)}px; }}
QPushButton#Flat:hover {{ background: {c['accent_soft']}; }}
QPushButton#HeaderButton {{ background: transparent; border: 1px solid transparent; font-weight: 600; padding: {px(8)}px {px(12)}px; }}
QPushButton#HeaderButton:hover {{ background: {c['surface2']}; border-color: {c['border']}; }}
QPushButton#Danger {{ color: {c['danger']}; }}
QToolButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: {px(6)}px {px(10)}px; }}
QToolButton:hover {{ background: {c['surface2']}; }}
QToolButton:disabled {{ color: {c['muted']}; }}

/* Tarjetas */
QFrame#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
QFrame#Card:hover {{ border: 2px solid {c['accent']}; background: {c['surface']}; }}
QLabel#CardTitle {{ font-size: {px(17)}px; font-weight: 700; }}
QLabel#CardText {{ color: {c['muted']}; font-size: {px(14)}px; }}
QFrame#Panel {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; }}
QFrame#DropZone {{ background: {c['surface']}; border: 2px dashed {c['border']}; border-radius: 14px; }}
QFrame#DropZone[hover="true"] {{ border: 2px dashed {c['accent']}; background: {c['accent_soft']}; }}
QFrame#FileChip {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 10px; }}
QFrame#Banner {{ background: {c['warn_soft']}; border: 1px solid {c['warn']}; border-radius: 10px; }}
QLabel#BannerText {{ color: {c['warn']}; }}
QFrame#Success {{ background: {c['ok_soft']}; border: 1px solid {c['ok']}; border-radius: 12px; }}
QLabel#SuccessTitle {{ color: {c['ok']}; font-size: {px(19)}px; font-weight: 700; }}
QFrame#Error {{ background: {c['danger_soft']}; border: 1px solid {c['danger']}; border-radius: 12px; }}
QLabel#ErrorText {{ color: {c['danger']}; }}

/* Controles */
QLineEdit, QSpinBox, QComboBox, QDoubleSpinBox {{ background: {c['surface']}; border: 1px solid {c['border']};
    border-radius: 8px; padding: {px(7)}px {px(10)}px; min-height: {px(22)}px; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 2px solid {c['accent']}; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']};
    selection-background-color: {c['accent_soft']}; selection-color: {c['text']}; padding: 4px; }}
QComboBox::drop-down {{ border: none; width: {px(26)}px; }}
QRadioButton, QCheckBox {{ spacing: {px(10)}px; padding: {px(5)}px 0; background: transparent; }}
QRadioButton::indicator {{ width: {px(18)}px; height: {px(18)}px; border-radius: {px(18)//2 + 2}px;
    border: 2px solid {c['muted']}; background: {c['surface']}; }}
QRadioButton::indicator:hover, QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QRadioButton::indicator:checked {{ border-color: {c['accent']};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 {c['accent']}, stop:0.48 {c['accent']}, stop:0.56 {c['surface']}, stop:1 {c['surface']}); }}
QCheckBox::indicator {{ width: {px(18)}px; height: {px(18)}px; border-radius: 5px; border: 2px solid {c['muted']}; background: {c['surface']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url({_ASSETS}/check.svg); }}
QSpinBox, QDoubleSpinBox {{ padding-right: {px(30)}px; }}
QPushButton:checked {{ background: {c['accent_soft']}; border: 2px solid {c['accent']}; color: {c['accent']}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: {px(26)}px;
    border-left: 1px solid {c['border']}; border-top-right-radius: 8px; background: {c['surface2']}; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: {px(26)}px;
    border-left: 1px solid {c['border']}; border-bottom-right-radius: 8px; background: {c['surface2']}; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background: {c['accent_soft']}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({_ASSETS}/up.svg); width: {px(11)}px; height: {px(11)}px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({_ASSETS}/down.svg); width: {px(11)}px; height: {px(11)}px; }}
QComboBox::down-arrow {{ image: url({_ASSETS}/down.svg); width: {px(13)}px; height: {px(13)}px; }}
QProgressBar {{ background: {c['surface2']}; border: none; border-radius: {px(7)}px; height: {px(14)}px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: {px(7)}px; }}
QSlider::groove:horizontal {{ height: 6px; background: {c['surface2']}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {c['accent']}; width: {px(20)}px; margin: -8px 0; border-radius: {px(10)}px; }}
QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 12px; padding: 6px; outline: 0; }}
QListWidget::item {{ border-radius: 8px; padding: 6px; color: {c['text']}; }}
QListWidget::item:selected {{ background: {c['accent_soft']}; border: 2px solid {c['accent']}; color: {c['text']}; }}
QListWidget::item:hover {{ background: {c['surface2']}; }}
QTextEdit, QPlainTextEdit {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 8px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
QMessageBox QLabel {{ font-size: {px(15)}px; }}
"""


def apply(app: QApplication, theme: str, scale: int):
    _current["theme"] = theme if theme in THEMES else "claro"
    _current["scale"] = max(80, min(170, int(scale)))
    c = colors()
    _write_assets(c)
    font = QFont(app.font())
    font.setPointSizeF(10.5 * _current["scale"] / 100.0)
    app.setFont(font)
    pal = app.palette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.Base, QColor(c["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["surface2"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["surface"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(c["accent_text"]))
    pal.setColor(QPalette.ToolTipBase, QColor(c["surface"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(build_qss(c))
