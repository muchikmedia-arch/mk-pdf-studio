"""MK PDF Studio - punto de entrada."""
import multiprocessing
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# En Windows (pythonw) no hay consola: evitar errores al escribir mensajes
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")



def _report_crash():
    """Guarda el error y lo muestra, para poder ayudar si algo falla al abrir."""
    import traceback
    text = traceback.format_exc()
    try:
        from mkpdf.config import user_data_dir
        with open(os.path.join(user_data_dir(), "errores.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, "MK PDF Studio no pudo abrirse.\n\nDetalle:\n" + text[-900:], "MK PDF Studio", 0x10)
        except Exception:
            pass


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        from mkpdf.app import run
        code = run()
    except Exception:
        _report_crash()
        code = 1
    sys.exit(code)
