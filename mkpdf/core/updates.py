"""Aviso de nuevas versiones.

El programa lee un archivo pequeño (version.json) publicado en GitHub. No envía ningún dato:
solo descarga ese archivo. Si no hay internet, no pasa nada.
"""
import hashlib
import json
import os
import re
import ssl
import tempfile
import urllib.request

from ..config import APP_VERSION

GITHUB_USER = "muchikmedia-arch"
GITHUB_REPO = "mk-pdf-studio"
VERSION_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/version.json"
RELEASES_PAGE = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
USER_AGENT = f"MKPDFStudio/{APP_VERSION} (Windows)"


def parse_version(v: str):
    nums = [int(x) for x in re.findall(r"\d+", v or "")[:4]]
    return tuple(nums + [0] * (4 - len(nums)))


def is_newer(remote: str, local: str = APP_VERSION) -> bool:
    return parse_version(remote) > parse_version(local)


def _context():
    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()   # certificados de Windows (incluye los de la red de la oficina)
    except Exception:
        pass
    return ctx


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=timeout, context=_context())


def fetch_latest(timeout: float = 8.0) -> dict:
    """Información de la última versión publicada. Lanza una excepción si no hay conexión."""
    with _open(VERSION_URL, timeout) as r:
        data = json.loads(r.read(200_000).decode("utf-8"))
    if not isinstance(data, dict) or "version" not in data:
        raise ValueError("Respuesta no válida")
    data["newer"] = is_newer(str(data["version"]))
    return data


def download_installer(info: dict, progress=None, cancelled=None) -> str:
    """Descarga el instalador a una carpeta temporal y comprueba que llegó completo."""
    url = info["installer"]
    if not url.startswith("https://"):
        raise ValueError("Dirección de descarga no válida")
    folder = os.path.join(tempfile.gettempdir(), "MK PDF Studio - actualización")
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(url.split("?")[0]) or f"MK-PDF-Studio-{info['version']}.exe"
    dst = os.path.join(folder, name)
    tmp = dst + ".parcial"
    h = hashlib.sha256()
    with _open(url, 30) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or info.get("size") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                raise InterruptedError()
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    expected = (info.get("sha256") or "").lower().strip()
    if expected and h.hexdigest() != expected:
        os.remove(tmp)
        raise ValueError("El archivo descargado está incompleto o dañado. Inténtalo de nuevo.")
    if os.path.exists(dst):
        os.remove(dst)
    os.replace(tmp, dst)
    return dst
