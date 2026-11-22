"""Datos generales del programa: nombre, versión, créditos y ajustes guardados."""
import json
import os
import sys

APP_NAME = "MK PDF Studio"
APP_VERSION = "1.3.1"
APP_EDITION = "Etapa 2"
APP_YEAR = "2026"
DEVELOPER = "Muchik Media | Apps"
LOCATION = "Trujillo - Perú"
COMPANY = "Muchik Media | Apps"
COMPANY_WEB = "www.muchikmedia.com"
COMPANY_EMAIL = "muchikmedia@gmail.com"
APP_ID = "MuchikMedia.MKPDFStudio"

# Carpeta del paquete (donde están los recursos: íconos, datos de OCR)
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
RES_DIR = os.path.join(PKG_DIR, "resources")


def user_data_dir() -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "MK PDF Studio")
    else:
        path = os.path.join(os.path.expanduser("~"), ".config", "mkpdfstudio")
    os.makedirs(path, exist_ok=True)
    return path


DEFAULTS = {
    "theme": "claro",            # claro | oscuro | azul | verde
    "text_scale": 100,           # porcentaje del tamaño de letra del programa
    "save_mode": "junto",        # junto | preguntar | carpeta
    "save_folder": "",
    "open_when_done": True,
    "ocr_lang": "spa",           # spa | spa+eng
    "ocr_quality": "precisa",    # rapida | precisa
    "scan_font": "Arial",        # fuente para documentos escaneados
    "confirm_signed": True,
    "last_dir": "",
    "signature_image": "",
    "stamp_title": "RECIBIDO",
    "stamp_area": "",
    "stamp_color": "azul",
    "stamp_date": True,
    "stamp_fields": True,
    "editor_font": "Arial",
    "editor_size": 12,
    "check_updates": True,
    "folio_color": "azul",
}


class Settings:
    def __init__(self):
        self.path = os.path.join(user_data_dir(), "ajustes.json")
        self.data = dict(DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update({k: v for k, v in stored.items() if k in DEFAULTS})
        except Exception:
            pass

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()

    def reset(self):
        keep_dir = self.data.get("last_dir", "")
        self.data = dict(DEFAULTS)
        self.data["last_dir"] = keep_dir
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


_settings = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
