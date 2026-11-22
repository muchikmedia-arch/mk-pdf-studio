"""Envolturas para ejecutar herramientas rápidas en segundo plano."""
from . import tools
from .common import NULL_PROGRESS


def protect_task(src, dst, password, progress=NULL_PROGRESS):
    progress(0.3, "Protegiendo el documento…")
    tools.protect(src, dst, password)
    return {}


def unprotect_task(src, dst, password, progress=NULL_PROGRESS):
    progress(0.3, "Quitando la contraseña…")
    tools.unprotect(src, dst, password)
    return {}
