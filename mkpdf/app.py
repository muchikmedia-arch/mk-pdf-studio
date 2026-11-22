"""Arranque del programa."""
import os
import sys


def _set_windows_app_id():
    """Solo cuando se ejecuta sin el lanzador propio (desarrollo con python.exe).

    Con el lanzador «MK PDF Studio.exe» Windows ya identifica el programa por su propio .exe
    y muestra su logo en la barra de tareas (y al anclarlo).
    """
    if sys.platform.startswith("win") and os.path.basename(sys.executable).lower().startswith("python"):
        try:
            import ctypes
            from .config import APP_ID
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def run():
    _set_windows_app_id()
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from .config import APP_NAME, settings
    from .ui import icons, theme
    from .ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Muchik Media")
    app.setStyle("Fusion")
    app.setWindowIcon(icons.app_icon())
    st = settings()
    theme.apply(app, st.get("theme"), st.get("text_scale"))
    win = MainWindow()
    screen = app.primaryScreen().availableGeometry()
    win.resize(min(win.width(), int(screen.width() * 0.92)), min(win.height(), int(screen.height() * 0.9)))
    win.move(screen.center() - win.rect().center())
    win.show()
    win.start_update_check()
    return app.exec()
