"""Ventanas de Ajustes y Acerca de."""
import os
import platform
import sys

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .widgets import icon_button
from ..config import (APP_EDITION, APP_NAME, APP_VERSION, APP_YEAR, COMPANY, COMPANY_EMAIL, COMPANY_WEB,
                      DEVELOPER, settings, user_data_dir)


def _section(text):
    l = QLabel(text)
    l.setObjectName("SectionTitle")
    return l


def _muted(text):
    l = QLabel(text)
    l.setObjectName("Muted")
    l.setWordWrap(True)
    return l


class SettingsDialog(QDialog):
    appearanceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ajustes")
        self.setMinimumSize(QSize(theme.px(620), theme.px(560)))
        st = settings()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(26, 20, 26, 10)
        lay.setSpacing(10)
        t = QLabel("Ajustes")
        t.setObjectName("PageTitle")
        lay.addWidget(t)

        # --- Apariencia ---
        lay.addWidget(_section("Apariencia"))
        lay.addWidget(_muted("Elige los colores del programa."))
        trow = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        for i, (key, data) in enumerate(theme.THEMES.items()):
            b = QPushButton(data["name"])
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(theme.px(54))
            b.setStyleSheet(
                f"QPushButton {{ background: {data['bg']}; color: {data['text']}; border: 2px solid {data['border']};"
                f" border-radius: 10px; font-weight: 600; padding: 8px 14px; }}"
                f"QPushButton:checked {{ border: 3px solid {data['accent']}; }}")
            b.setProperty("key", key)
            self.theme_group.addButton(b, i)
            trow.addWidget(b)
            if key == st.get("theme"):
                b.setChecked(True)
        lay.addLayout(trow)
        self.theme_group.buttonClicked.connect(self._theme_changed)

        lay.addSpacing(6)
        lay.addWidget(_section("Tamaño de las letras"))
        lay.addWidget(_muted("Si te cuesta leer, aumenta el tamaño. Se aplica a todo el programa."))
        srow = QHBoxLayout()
        small = QLabel("A")
        small.setStyleSheet("font-size: 13px; font-weight: 700;")
        big = QLabel("A")
        big.setStyleSheet("font-size: 26px; font-weight: 700;")
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(85, 160)
        self.scale.setSingleStep(5)
        self.scale.setPageStep(15)
        self.scale.setValue(int(st.get("text_scale")))
        self.scale_label = QLabel()
        self.scale_label.setMinimumWidth(theme.px(110))
        srow.addWidget(small)
        srow.addWidget(self.scale, 1)
        srow.addWidget(big)
        srow.addWidget(self.scale_label)
        lay.addLayout(srow)
        prow = QHBoxLayout()
        for txt, val in (("Normal", 100), ("Grande", 120), ("Muy grande", 140)):
            b = QPushButton(txt)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, v=val: self.scale.setValue(v))
            prow.addWidget(b)
        prow.addStretch(1)
        lay.addLayout(prow)
        self.scale.valueChanged.connect(self._scale_moved)
        self.scale.sliderReleased.connect(self._scale_apply)
        self._scale_text()

        # --- Guardado ---
        lay.addSpacing(6)
        lay.addWidget(_section("Dónde guardar los archivos nuevos"))
        self.save_group = QButtonGroup(self)
        modes = [("junto", "En la misma carpeta del archivo original (recomendado)"),
                 ("preguntar", "Preguntarme cada vez"),
                 ("carpeta", "Siempre en esta carpeta:")]
        for i, (k, t) in enumerate(modes):
            rb = QRadioButton(t)
            rb.setProperty("key", k)
            self.save_group.addButton(rb, i)
            lay.addWidget(rb)
            if st.get("save_mode") == k:
                rb.setChecked(True)
        frow = QHBoxLayout()
        self.folder = QLineEdit(st.get("save_folder"))
        self.folder.setReadOnly(True)
        self.folder.setPlaceholderText("Ninguna carpeta elegida")
        pick = icon_button("Elegir…", "folder")
        pick.clicked.connect(self._pick_folder)
        frow.addSpacing(theme.px(30))
        frow.addWidget(self.folder, 1)
        frow.addWidget(pick)
        lay.addLayout(frow)
        self.open_done = QCheckBox("Abrir el archivo automáticamente cuando termine")
        self.open_done.setChecked(bool(st.get("open_when_done")))
        lay.addWidget(self.open_done)

        # --- OCR ---
        lay.addSpacing(6)
        lay.addWidget(_section("Reconocimiento de texto (OCR)"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        self.lang = QComboBox()
        self.lang.addItem("Español", "spa")
        self.lang.addItem("Español e inglés", "spa+eng")
        self.lang.setCurrentIndex(0 if st.get("ocr_lang") == "spa" else 1)
        self.quality = QComboBox()
        self.quality.addItem("Precisa (recomendada)", "precisa")
        self.quality.addItem("Rápida (para computadoras lentas)", "rapida")
        self.quality.setCurrentIndex(0 if st.get("ocr_quality") != "rapida" else 1)
        self.font = QComboBox()
        for f in ("Arial", "Times New Roman", "Calibri"):
            self.font.addItem(f, f)
        self.font.setCurrentText(st.get("scan_font") or "Arial")
        grid.addWidget(QLabel("Idioma de los documentos:"), 0, 0)
        grid.addWidget(self.lang, 0, 1)
        grid.addWidget(QLabel("Calidad:"), 1, 0)
        grid.addWidget(self.quality, 1, 1)
        grid.addWidget(QLabel("Letra para documentos escaneados:"), 2, 0)
        grid.addWidget(self.font, 2, 1)
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)

        lay.addSpacing(6)
        lay.addWidget(_section("Avisos"))
        self.signed = QCheckBox("Avisarme cuando un PDF tiene firma digital antes de modificarlo")
        self.signed.setChecked(bool(st.get("confirm_signed")))
        lay.addWidget(self.signed)
        self.updates = QCheckBox("Avisarme cuando haya una nueva versión del programa (necesita internet)")
        self.updates.setChecked(bool(st.get("check_updates")))
        lay.addWidget(self.updates)
        urow = QHBoxLayout()
        now = QPushButton("Buscar actualizaciones ahora")
        now.clicked.connect(self._check_now)
        urow.addWidget(now)
        urow.addStretch(1)
        lay.addLayout(urow)
        lay.addStretch(1)

        # --- botones ---
        btns = QHBoxLayout()
        btns.setContentsMargins(26, 10, 26, 18)
        reset = QPushButton("Restablecer valores")
        reset.setObjectName("Flat")
        reset.clicked.connect(self._reset)
        btns.addWidget(reset)
        btns.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Guardar ajustes")
        ok.setObjectName("Primary")
        ok.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)
        self._orig_theme = st.get("theme")
        self._orig_scale = st.get("text_scale")

    def _scale_text(self):
        v = self.scale.value()
        name = "Normal" if v < 110 else "Grande" if v < 130 else "Muy grande"
        self.scale_label.setText(f"{name} ({v}%)")

    def _scale_moved(self, v):
        self._scale_text()
        if not self.scale.isSliderDown():
            self._scale_apply()

    def _scale_apply(self):
        settings().data["text_scale"] = self.scale.value()
        self.appearanceChanged.emit()

    def _theme_changed(self, b):
        settings().data["theme"] = b.property("key")
        self.appearanceChanged.emit()

    def _check_now(self):
        from .updater import manual_check
        manual_check(self, self.parent())

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Carpeta para guardar", self.folder.text() or os.path.expanduser("~"))
        if d:
            self.folder.setText(d)
            self.save_group.button(2).setChecked(True)

    def _reset(self):
        settings().reset()
        self.appearanceChanged.emit()
        self.accept()

    def _save(self):
        st = settings()
        b = self.save_group.checkedButton()
        mode = b.property("key") if b else "junto"
        if mode == "carpeta" and not self.folder.text():
            mode = "junto"
        st.data.update({
            "save_mode": mode,
            "save_folder": self.folder.text(),
            "open_when_done": self.open_done.isChecked(),
            "ocr_lang": self.lang.currentData(),
            "ocr_quality": self.quality.currentData(),
            "scan_font": self.font.currentData(),
            "confirm_signed": self.signed.isChecked(),
            "check_updates": self.updates.isChecked(),
            "theme": settings().data.get("theme"),
            "text_scale": self.scale.value(),
        })
        st.save()
        self.accept()

    def reject(self):
        settings().data["theme"] = self._orig_theme
        settings().data["text_scale"] = self._orig_scale
        self.appearanceChanged.emit()
        super().reject()


def _about_check(dlg):
    from .updater import manual_check
    manual_check(dlg, dlg.parent())


COMPONENTS = [
    ("PyMuPDF / MuPDF", "Artifex Software", "AGPL-3.0"),
    ("Tesseract OCR", "Google y colaboradores", "Apache-2.0"),
    ("pdf2docx", "Artifex y colaboradores", "MIT"),
    ("Qt / PySide6", "The Qt Company", "LGPL-3.0"),
    ("OpenCV", "OpenCV.org", "Apache-2.0"),
    ("NumPy", "NumPy Developers", "BSD"),
    ("openpyxl", "Eric Gazoni, Charlie Clark", "MIT"),
    ("python-docx", "Steve Canny", "MIT"),
    ("python-pptx", "Steve Canny", "MIT"),
    ("Pillow", "Jeffrey A. Clark y colaboradores", "MIT-CMU"),
    ("Python", "Python Software Foundation", "PSF"),
]


class AboutDialog(QDialog):
    def _check_updates(self):
        _about_check(self)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Acerca de {APP_NAME}")
        self.setMinimumSize(QSize(theme.px(560), theme.px(560)))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(30, 24, 30, 10)
        lay.setSpacing(6)
        c = theme.colors()

        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(theme.px(96)))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        name = QLabel(APP_NAME)
        name.setObjectName("PageTitle")
        name.setAlignment(Qt.AlignCenter)
        lay.addWidget(name)
        ver = QLabel(f"Versión {APP_VERSION}")
        ver.setObjectName("Muted")
        ver.setAlignment(Qt.AlignCenter)
        lay.addWidget(ver)
        lay.addSpacing(10)

        card = QFrame()
        card.setObjectName("Panel")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(6)
        dev_t = QLabel("Desarrollado por")
        dev_t.setObjectName("Muted")
        dev_t.setAlignment(Qt.AlignCenter)
        dev = QLabel(DEVELOPER)
        dev.setObjectName("Big")
        dev.setAlignment(Qt.AlignCenter)
        comp = QLabel(COMPANY)
        comp.setAlignment(Qt.AlignCenter)
        comp.setStyleSheet("font-weight: 600;")
        web = QLabel(f'Web: <a href="https://{COMPANY_WEB}" style="color:{c["accent"]}">{COMPANY_WEB}</a>')
        web.setOpenExternalLinks(True)
        web.setAlignment(Qt.AlignCenter)
        mail = QLabel(f'Correo: <a href="mailto:{COMPANY_EMAIL}" style="color:{c["accent"]}">{COMPANY_EMAIL}</a>')
        mail.setOpenExternalLinks(True)
        mail.setAlignment(Qt.AlignCenter)
        for w in (dev_t, dev, comp, web, mail):
            cl.addWidget(w)
        lay.addWidget(card)

        lay.addSpacing(8)
        desc = _muted("Programa gratuito para convertir, organizar y preparar documentos PDF en la oficina. "
                      "Funciona sin internet: tus documentos nunca salen de tu computadora.")
        desc.setAlignment(Qt.AlignCenter)
        lay.addWidget(desc)
        copy = QLabel(f"© {APP_YEAR} {DEVELOPER} · {COMPANY}")
        copy.setAlignment(Qt.AlignCenter)
        copy.setObjectName("Muted")
        lay.addWidget(copy)

        lay.addSpacing(10)
        lay.addWidget(_section("Componentes de código abierto"))
        lic = _muted("MK PDF Studio se distribuye gratis como software libre bajo la licencia AGPL-3.0, "
                     "con su código fuente incluido en la carpeta del programa. Usa estos componentes:")
        lay.addWidget(lic)
        g = QGridLayout()
        g.setHorizontalSpacing(16)
        for i, (n, a, l) in enumerate(COMPONENTS):
            nl = QLabel(n)
            nl.setStyleSheet("font-weight: 600;")
            al = QLabel(a)
            al.setObjectName("Muted")
            ll = QLabel(l)
            ll.setObjectName("Muted")
            g.addWidget(nl, i, 0)
            g.addWidget(al, i, 1)
            g.addWidget(ll, i, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)

        lay.addSpacing(8)
        lay.addWidget(_section("Información técnica"))
        self.tech = (f"{APP_NAME} {APP_VERSION}\n"
                     f"Sistema: {platform.system()} {platform.release()} ({platform.machine()})\n"
                     f"Python {platform.python_version()}\n"
                     f"Ajustes y registro de errores: {user_data_dir()}")
        tl = QLabel(self.tech)
        tl.setObjectName("Muted")
        tl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tl.setWordWrap(True)
        lay.addWidget(tl)
        lay.addStretch(1)

        btns = QHBoxLayout()
        btns.setContentsMargins(30, 10, 30, 18)
        cp = QPushButton("Copiar información técnica")
        cp.setObjectName("Flat")
        cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.tech))
        btns.addWidget(cp)
        upd = QPushButton("Buscar actualizaciones")
        upd.clicked.connect(self._check_updates)
        btns.addWidget(upd)
        btns.addStretch(1)
        close = QPushButton("Cerrar")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        outer.addLayout(btns)
