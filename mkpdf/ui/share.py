"""Compartir el programa por WhatsApp, Messenger o correo, con instrucciones de instalación."""
import os
import shutil
import sys
import threading
from urllib.parse import quote

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout)

from . import theme
from .widgets import icon_button, inform, show_in_folder
from ..config import APP_NAME, COMPANY, COMPANY_WEB, DEVELOPER
from ..core import updates

DOWNLOAD_LINK = (f"https://github.com/{updates.GITHUB_USER}/{updates.GITHUB_REPO}/raw/"
                 f"{updates.DOWNLOAD_BRANCH}/MK-PDF-Studio-Instalador.exe")
PAGE_LINK = f"https://github.com/{updates.GITHUB_USER}/{updates.GITHUB_REPO}"

INSTRUCTIONS = (
    "Cómo instalarlo:\n"
    "1. Abre el archivo descargado (MK-PDF-Studio-Instalador.exe).\n"
    "2. Si aparece la pantalla azul «Windows protegió su PC», haz clic en «Más información» y luego en "
    "«Ejecutar de todas formas». Ese aviso sale porque es un programa nuevo que todavía no tiene un "
    "certificado de firma; el programa es seguro.\n"
    "3. Dale «Siguiente» hasta terminar. No necesita permisos de administrador.\n"
)


def share_message(bold="*"):
    b = bold
    return (f"Te comparto {b}{APP_NAME}{b}, un programa gratuito para convertir PDF a Word, Excel y PowerPoint, "
            "editar PDF (texto, firmas, sellos), foliar, unir, comprimir y más. Funciona sin internet.\n\n"
            f"Descárgalo aquí:\n{DOWNLOAD_LINK}\n\n"
            f"{INSTRUCTIONS}\n"
            f"Más información: {PAGE_LINK}\n"
            f"Desarrollado por {DEVELOPER} – {COMPANY} ({COMPANY_WEB})")


def _has_protocol(name):
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, name))
        return True
    except Exception:
        return False


class ShareDialog(QDialog):
    _progress = Signal(int, int)
    _done = Signal(str)
    _failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Compartir {APP_NAME}")
        self.setMinimumSize(QSize(theme.px(640), theme.px(600)))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        t = QLabel(f"Compartir {APP_NAME}")
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        sub = QLabel("Envía el programa a tus compañeros. El mensaje ya incluye el enlace de descarga y cómo "
                     "instalarlo si aparece el aviso azul de Windows. Puedes cambiar el texto antes de enviarlo.")
        sub.setObjectName("Muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        self.text = QPlainTextEdit(share_message())
        self.text.setMinimumHeight(theme.px(230))
        lay.addWidget(self.text, 1)
        row = QHBoxLayout()
        wa = icon_button("WhatsApp", "whatsapp", "Primary")
        wa.clicked.connect(self.whatsapp)
        ms = icon_button("Messenger", "chat")
        ms.clicked.connect(self.messenger)
        mail = icon_button("Correo", "mail")
        menu = QMenu(mail)
        menu.addAction("Gmail", self.gmail)
        menu.addAction("Outlook u otro programa de correo", self.mailto)
        mail.setMenu(menu)
        cp = icon_button("Copiar mensaje", "copy")
        cp.clicked.connect(self.copy)
        for b in (wa, ms, mail, cp):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {theme.colors()['border']};")
        lay.addWidget(line)
        usb_t = QLabel("Pasarlo por USB o carpeta compartida")
        usb_t.setObjectName("SectionTitle")
        lay.addWidget(usb_t)
        usb = QLabel("Descarga el instalador a una USB o a una carpeta de la red de la oficina. "
                     "Copiado así, normalmente no aparece el aviso azul de Windows.")
        usb.setObjectName("Muted")
        usb.setWordWrap(True)
        lay.addWidget(usb)
        urow = QHBoxLayout()
        self.usb_btn = icon_button("Guardar el instalador en…", "folder")
        self.usb_btn.clicked.connect(self.save_installer)
        urow.addWidget(self.usb_btn)
        urow.addStretch(1)
        lay.addLayout(urow)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.hide()
        lay.addWidget(self.bar)
        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        lay.addLayout(close_row)
        self._progress.connect(self._on_progress)
        self._done.connect(self._on_done)
        self._failed.connect(self._on_failed)
        self._folder = ""

    def msg(self, plain=False):
        t = self.text.toPlainText()
        return t.replace("*", "") if plain else t

    def copy(self):
        QGuiApplication.clipboard().setText(self.msg())
        self.status.setText("Mensaje copiado. Pégalo donde quieras con Ctrl+V.")

    def whatsapp(self):
        text = quote(self.msg())
        if _has_protocol("whatsapp"):
            QDesktopServices.openUrl(QUrl(f"whatsapp://send?text={text}", QUrl.TolerantMode))
            self.status.setText("Se abrió WhatsApp con el mensaje listo: elige el contacto o grupo y envíalo.")
        else:
            QDesktopServices.openUrl(QUrl(f"https://wa.me/?text={text}", QUrl.TolerantMode))
            self.status.setText("Se abrió WhatsApp en el navegador con el mensaje listo: elige el contacto y envíalo.")

    def messenger(self):
        QGuiApplication.clipboard().setText(self.msg(plain=True))
        QDesktopServices.openUrl(QUrl("https://www.messenger.com/"))
        self.status.setText("Se copió el mensaje y se abrió Messenger: entra al chat y pégalo con Ctrl+V.")

    def gmail(self):
        url = ("https://mail.google.com/mail/?view=cm&fs=1&su=" + quote(f"Te comparto {APP_NAME}")
               + "&body=" + quote(self.msg(plain=True)))
        QDesktopServices.openUrl(QUrl(url, QUrl.TolerantMode))
        self.status.setText("Se abrió Gmail con el correo listo: escribe a quién enviarlo.")

    def mailto(self):
        url = "mailto:?subject=" + quote(f"Te comparto {APP_NAME}") + "&body=" + quote(self.msg(plain=True))
        if not QDesktopServices.openUrl(QUrl(url, QUrl.TolerantMode)):
            self.copy()
            self.status.setText("No hay un programa de correo configurado. El mensaje se copió: pégalo en tu correo.")
        else:
            self.status.setText("Se abrió tu programa de correo con el mensaje listo.")

    # --- instalador para USB ---
    def save_installer(self):
        folder = QFileDialog.getExistingDirectory(self, "¿Dónde guardar el instalador? (por ejemplo tu USB)")
        if not folder:
            return
        self._folder = folder
        self.usb_btn.setEnabled(False)
        self.bar.setValue(0)
        self.bar.show()
        self.status.setText("Buscando la versión más reciente…")

        def run():
            try:
                info = updates.fetch_latest()
                path = updates.download_installer(info, progress=lambda d, t: self._progress.emit(d, t))
                name = f"MK-PDF-Studio-Instalador-{info['version']}.exe"
                dst = os.path.join(folder, name)
                shutil.copyfile(path, dst)
                with open(os.path.join(folder, "Cómo instalar MK PDF Studio.txt"), "w", encoding="utf-8") as f:
                    f.write(f"{APP_NAME} {info['version']}\n\n" + INSTRUCTIONS.replace(
                        "MK-PDF-Studio-Instalador.exe", name) + f"\nMás información: {PAGE_LINK}\n")
                self._done.emit(dst)
            except Exception as e:
                self._failed.emit(str(e))
        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, d, t):
        if t:
            self.bar.setValue(int(1000 * d / t))
            self.status.setText(f"Descargando el instalador… {d // 1_000_000} de {t // 1_000_000} MB")

    def _on_done(self, path):
        self.bar.hide()
        self.usb_btn.setEnabled(True)
        self.status.setText(f"Listo: se guardó «{os.path.basename(path)}» y las instrucciones en la carpeta elegida.")
        show_in_folder(path)

    def _on_failed(self, text):
        self.bar.hide()
        self.usb_btn.setEnabled(True)
        self.status.setText("No se pudo descargar el instalador. Revisa tu conexión a internet. "
                            f"Detalle: {text[:160]}")
