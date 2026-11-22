"""Aviso de actualización: franja en la ventana principal y ventana para actualizar con un clic."""
import os
import subprocess
import sys
import threading

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QVBoxLayout)

from . import theme
from .widgets import IconLabel, ask, icon_button, inform
from ..config import APP_NAME, APP_VERSION
from ..core import updates


class UpdateChecker(QObject):
    found = Signal(dict)       # hay una versión nueva
    result = Signal(object)    # dict con la información, o str con el error

    def check(self, manual=False):
        def run():
            try:
                info = updates.fetch_latest()
                self.result.emit(info)
                if info.get("newer"):
                    self.found.emit(info)
            except Exception as e:
                self.result.emit(str(e) or "sin conexión")
        threading.Thread(target=run, daemon=True).start()


class UpdateBar(QFrame):
    """Franja discreta debajo del encabezado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UpdateBar")
        self.info = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 8, 16, 8)
        lay.setSpacing(12)
        self.ic = IconLabel("upload", 22)
        lay.addWidget(self.ic)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text, 1)
        self.notes_btn = QPushButton("Ver novedades")
        self.notes_btn.setObjectName("Flat")
        self.notes_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn = icon_button("Actualizar ahora", "check", "Primary")
        self.later_btn = QPushButton("Más tarde")
        self.later_btn.setObjectName("Flat")
        self.later_btn.setCursor(Qt.PointingHandCursor)
        for b in (self.notes_btn, self.update_btn, self.later_btn):
            lay.addWidget(b)
        self.later_btn.clicked.connect(self.hide)
        self.restyle()
        self.hide()

    def restyle(self):
        c = theme.colors()
        self.setStyleSheet(f"QFrame#UpdateBar {{ background: {c['ok_soft']}; border-bottom: 1px solid {c['ok']}; }}"
                           f"QPushButton#Primary {{ padding: {theme.px(7)}px {theme.px(16)}px; font-size: {theme.px(15)}px; }}")
        self.ic.refresh()

    def show_info(self, info):
        self.info = info
        self.text.setText(f"<b>Hay una nueva versión de {APP_NAME}: {info['version']}</b>"
                          f" &nbsp;·&nbsp; tienes la {APP_VERSION}. Actualizar toma un minuto y no pierdes nada.")
        self.show()


class UpdateDialog(QDialog):
    """Muestra las novedades, descarga el instalador y lo abre."""
    _progress = Signal(int, int)
    _done = Signal(str)
    _failed = Signal(str)

    def __init__(self, info, main_window=None):
        super().__init__(main_window)
        self.info = info
        self.main_window = main_window
        self.cancel_flag = False
        self.setWindowTitle("Actualizar MK PDF Studio")
        self.setMinimumWidth(theme.px(560))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        t = QLabel(f"Nueva versión {info['version']}")
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        date = str(info.get("date") or "")
        if len(date) == 10 and date[4] == "-":
            date = f"{date[8:10]}/{date[5:7]}/{date[0:4]}"
        sub = QLabel(f"Tienes la versión {APP_VERSION}." + (f"  Publicada el {date}." if date else ""))
        sub.setObjectName("Muted")
        lay.addWidget(sub)
        notes = info.get("notes") or []
        if notes:
            h = QLabel("Novedades")
            h.setObjectName("SectionTitle")
            lay.addWidget(h)
            nl = QLabel("".join(f"• {n}<br>" for n in notes))
            nl.setWordWrap(True)
            nl.setTextFormat(Qt.RichText)
            lay.addWidget(nl)
        self.msg = QLabel("Al pulsar «Actualizar» se descarga la nueva versión (unos "
                          f"{max(1, int((info.get('size') or 75_000_000) / 1_000_000))} MB). Luego el programa se "
                          "cierra, se instala solo y se vuelve a abrir. Tus ajustes, firmas y sellos se conservan.")
        self.msg.setObjectName("Muted")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.err = QLabel()
        self.err.setObjectName("ErrorText")
        self.err.setWordWrap(True)
        self.err.hide()
        lay.addWidget(self.err)
        row = QHBoxLayout()
        self.web_btn = QPushButton("Descargar desde la web")
        self.web_btn.setObjectName("Flat")
        self.web_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(updates.RELEASES_PAGE)))
        row.addWidget(self.web_btn)
        row.addStretch(1)
        self.cancel_btn = QPushButton("Ahora no")
        self.cancel_btn.clicked.connect(self._cancel)
        self.go_btn = QPushButton("Actualizar")
        self.go_btn.setObjectName("Primary")
        self.go_btn.clicked.connect(self._start)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.go_btn)
        lay.addLayout(row)
        self._progress.connect(self._on_progress)
        self._done.connect(self._on_done)
        self._failed.connect(self._on_failed)

    def _cancel(self):
        self.cancel_flag = True
        self.reject()

    def _start(self):
        mw = self.main_window
        if mw is not None and hasattr(mw, "editor") and mw.editor.has_unsaved():
            if not ask(self, "Cambios sin guardar", "En «Editar PDF» hay cambios sin guardar. Si actualizas ahora "
                       "se perderán. ¿Continuar?", "Actualizar igual", "Volver"):
                return
        self.go_btn.setEnabled(False)
        self.web_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelar")
        self.err.hide()
        self.bar.show()
        self.msg.setText("Descargando la nueva versión…")

        def run():
            try:
                path = updates.download_installer(self.info, progress=lambda d, t: self._progress.emit(d, t),
                                                  cancelled=lambda: self.cancel_flag)
                self._done.emit(path)
            except InterruptedError:
                pass
            except Exception as e:
                self._failed.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, done, total):
        if total:
            self.bar.setValue(int(1000 * done / total))
            self.msg.setText(f"Descargando la nueva versión… {done // 1_000_000} de {total // 1_000_000} MB")
        else:
            self.bar.setRange(0, 0)

    def _on_failed(self, text):
        self.bar.hide()
        self.go_btn.setEnabled(True)
        self.web_btn.setEnabled(True)
        self.cancel_btn.setText("Ahora no")
        self.err.setText("No se pudo descargar la actualización. Revisa tu conexión a internet e inténtalo de nuevo, "
                         f"o usa «Descargar desde la web».\nDetalle: {text[:200]}")
        self.err.show()
        self.msg.setText("")

    def _on_done(self, path):
        self.msg.setText("Listo. El programa se cerrará y se instalará la nueva versión…")
        self.bar.setValue(1000)
        QApplication.processEvents()
        try:
            flags = 0x00000008 | 0x00000200 if sys.platform.startswith("win") else 0  # DETACHED | NEW_GROUP
            subprocess.Popen([path, "/ACTUALIZAR"], close_fds=True, creationflags=flags)
        except Exception as e:
            self._on_failed(f"No se pudo abrir el instalador: {e}")
            return
        if self.main_window is not None and hasattr(self.main_window, "editor"):
            self.main_window.editor.dirty = False
        QTimer.singleShot(400, QApplication.instance().quit)
        self.accept()


def manual_check(parent, main_window=None):
    """Botón «Buscar actualizaciones»: revisa ahora y muestra el resultado."""
    from PySide6.QtCore import QEventLoop
    checker = UpdateChecker(parent)
    box = {}
    loop = QEventLoop()

    def got(res):
        box["r"] = res
        loop.quit()
    checker.result.connect(got)
    QApplication.setOverrideCursor(Qt.WaitCursor)
    checker.check(manual=True)
    QTimer.singleShot(15000, loop.quit)
    loop.exec()
    QApplication.restoreOverrideCursor()
    res = box.get("r")
    if isinstance(res, dict):
        if res.get("newer"):
            UpdateDialog(res, main_window).exec()
        else:
            inform(parent, "Actualizaciones", f"Tienes la versión más reciente ({APP_VERSION}).")
    else:
        inform(parent, "Actualizaciones", "No se pudo revisar si hay una versión nueva. "
               "Revisa tu conexión a internet e inténtalo más tarde.", error=True)
