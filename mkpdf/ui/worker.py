"""Ejecuta las tareas pesadas en un proceso aparte para que la ventana nunca se congele."""
import importlib
import multiprocessing as mp
import os
import queue
import traceback

from PySide6.QtCore import QObject, QTimer, Signal


def _child(func_path, args, kwargs, q):
    """Se ejecuta en el proceso hijo."""
    try:
        from ..core.common import Progress, UserError, Cancelled
        mod_name, func_name = func_path.split(":")
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)

        last = {"t": 0.0}

        def cb(frac, msg):
            q.put(("progress", frac, msg))

        result = func(*args, progress=Progress(cb), **kwargs)
        q.put(("done", result))
    except Exception as e:  # noqa
        try:
            from ..core.common import UserError
            if isinstance(e, UserError):
                q.put(("error", str(e), ""))
                return
        except Exception:
            pass
        tb = traceback.format_exc()
        msg = _friendly(e)
        q.put(("error", msg, tb))


def _friendly(e: Exception) -> str:
    text = str(e)
    if isinstance(e, PermissionError):
        return ("No se pudo guardar el archivo. Puede que esté abierto en otro programa (por ejemplo Word o "
                "el lector de PDF). Ciérralo e inténtalo de nuevo.")
    if isinstance(e, MemoryError):
        return "El documento es demasiado grande para la memoria disponible. Prueba con menos páginas a la vez."
    if "password" in text.lower() or "encrypted" in text.lower():
        return "El PDF tiene contraseña. Primero quítala en Herramientas > Contraseña."
    return f"Ocurrió un problema inesperado: {text[:300]}"


class TaskRunner(QObject):
    progress = Signal(float, str)
    finished = Signal(object)
    failed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self.q = None
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._poll)
        self._done = False

    def running(self):
        return self.proc is not None and self.proc.is_alive()

    def start(self, func_path, *args, **kwargs):
        ctx = mp.get_context("spawn")
        self.q = ctx.Queue()
        self._done = False
        self.proc = ctx.Process(target=_child, args=(func_path, args, kwargs, self.q), daemon=True)
        self.proc.start()
        self.timer.start()

    def cancel(self):
        if self.proc and self.proc.is_alive():
            self.proc.terminate()
            self.proc.join(2)
        self._stop()

    def _stop(self):
        self.timer.stop()
        self.proc = None
        self.q = None

    def _poll(self):
        if self.q is None:
            return
        last_progress = None
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "progress":
                    last_progress = item
                elif kind == "done":
                    self._done = True
                    if last_progress:
                        self.progress.emit(1.0, last_progress[2])
                    self._stop()
                    self.finished.emit(item[1])
                    return
                elif kind == "error":
                    self._done = True
                    self._stop()
                    self.failed.emit(item[1], item[2])
                    return
        except queue.Empty:
            pass
        except Exception:
            pass
        if last_progress:
            self.progress.emit(last_progress[1], last_progress[2])
        if self.proc is not None and not self.proc.is_alive() and not self._done:
            code = self.proc.exitcode
            self._stop()
            self.failed.emit("El proceso se detuvo inesperadamente (código %s). Inténtalo de nuevo." % code, "")
