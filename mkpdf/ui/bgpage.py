"""Herramienta: quitar el fondo a una firma o sello (PNG transparente) y mejorar su color."""
import os

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget)

from . import theme
from .widgets import (DropZone, ErrorPanel, FileChip, ResultPanel, StepHeader, choose_output, icon_button,
                      inform, open_path)
from ..config import settings
from ..core import bgremove
from ..core import editor_core as ec

COLOR_CHOICES = [("original", "Color original"), ("azul", "Azul (lapicero)"), ("negro", "Negro"),
                 ("rojo", "Rojo"), ("morado", "Morado (tinta de sello)"), ("azul_sello", "Azul (tinta de sello)")]


def _checker(w, h, cell=12):
    img = QPixmap(w, h)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    c = QColor("#D9DDE4")
    for y in range(0, h, cell):
        for x in range((y // cell) % 2 * cell, w, cell * 2):
            p.fillRect(x, y, cell, cell, c)
    p.end()
    return img


def _to_qimage(arr):
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.shape[2] == 4:
        return QImage(arr.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
    return QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class PreviewBox(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(QSize(theme.px(320), theme.px(240)))
        self.setFrameShape(QFrame.StyledPanel)
        self.img = None
        self.mode = "checker"

    def set_image(self, qimg):
        self.img = qimg
        self._paint()

    def set_mode(self, mode):
        self.mode = mode
        self._paint()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._paint()

    def _paint(self):
        w, h = max(10, self.width() - 4), max(10, self.height() - 4)
        if self.mode == "checker":
            canvas = _checker(w, h)
        else:
            canvas = QPixmap(w, h)
            canvas.fill(QColor("#FFFFFF" if self.mode == "white" else "#2B2F38"))
        if self.img is not None and not self.img.isNull():
            sc = self.img.scaled(int(w * 0.94), int(h * 0.94), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p = QPainter(canvas)
            p.drawImage((w - sc.width()) // 2, (h - sc.height()) // 2, sc)
            p.end()
        self.setPixmap(canvas)


class BgRemovePage(QWidget):
    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.path = ""
        self.small = None
        self.result_small = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        self.scroll = scroll
        inner = QWidget()
        inner.setObjectName("Page")
        scroll.setWidget(inner)
        center = QHBoxLayout(inner)
        center.setContentsMargins(24, 16, 24, 24)
        content = QWidget()
        content.setMaximumWidth(1000)
        center.addStretch(1)
        center.addWidget(content, 100)
        center.addStretch(1)
        body = QVBoxLayout(content)
        body.setSpacing(12)

        top = QHBoxLayout()
        back = icon_button("Volver", "back", "Flat")
        back.clicked.connect(self.backRequested)
        top.addWidget(back)
        top.addStretch(1)
        body.addLayout(top)
        t = QLabel("Quitar fondo a firma o sello")
        t.setObjectName("PageTitle")
        body.addWidget(t)
        s = QLabel("Deja tu firma o sello escaneado (o fotografiado con el celular) sin fondo, como imagen PNG "
                   "transparente para ponerla sobre cualquier documento. También puedes darle más color.")
        s.setObjectName("Muted")
        s.setWordWrap(True)
        body.addWidget(s)

        body.addWidget(StepHeader(1, "Elige la imagen de la firma o sello"))
        self.drop = DropZone("images", False, "Arrastra aquí la foto o el escaneo de la firma o sello")
        self.drop.filesChosen.connect(lambda f: self.load(f[0]))
        body.addWidget(self.drop)
        self.chip = FileChip()
        self.chip.changeRequested.connect(self.drop.browse)
        self.chip.hide()
        body.addWidget(self.chip)

        self.step2 = StepHeader(2, "Revisa y ajusta")
        body.addWidget(self.step2)
        self.panel = QFrame()
        self.panel.setObjectName("Panel")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(18, 14, 18, 14)
        pl.setSpacing(10)
        prev_row = QHBoxLayout()
        lcol, rcol = QVBoxLayout(), QVBoxLayout()
        la, lb = QLabel("Original"), QLabel("Sin fondo")
        for l in (la, lb):
            l.setObjectName("SectionTitle")
        self.before = PreviewBox()
        self.before.mode = "white"
        self.after = PreviewBox()
        lcol.addWidget(la)
        lcol.addWidget(self.before, 1)
        rcol.addWidget(lb)
        rcol.addWidget(self.after, 1)
        prev_row.addLayout(lcol, 1)
        prev_row.addLayout(rcol, 1)
        pl.addLayout(prev_row)
        mrow = QHBoxLayout()
        mrow.addStretch(1)
        mrow.addWidget(QLabel("Ver sobre:"))
        self.view_group = QButtonGroup(self)
        for i, (k, txt) in enumerate((("checker", "Cuadritos (transparente)"), ("white", "Hoja blanca"),
                                      ("dark", "Fondo oscuro"))):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setProperty("key", k)
            self.view_group.addButton(b, i)
            mrow.addWidget(b)
            if k == "checker":
                b.setChecked(True)
        self.view_group.idClicked.connect(lambda i: self.after.set_mode(self.view_group.button(i).property("key")))
        pl.addLayout(mrow)

        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        self.sens = QSlider(Qt.Horizontal)
        self.sens.setRange(0, 100)
        self.sens.setValue(50)
        srow = QHBoxLayout()
        srow.addWidget(QLabel("Menos"))
        srow.addWidget(self.sens, 1)
        srow.addWidget(QLabel("Más"))
        g.addWidget(QLabel("Sensibilidad:"), 0, 0)
        g.addLayout(srow, 0, 1)
        g.addWidget(QLabel("Color de la tinta:"), 1, 0)
        self.color = QComboBox()
        for k, txt in COLOR_CHOICES:
            self.color.addItem(txt, k)
        g.addWidget(self.color, 1, 1)
        self.inten = QSlider(Qt.Horizontal)
        self.inten.setRange(50, 200)
        self.inten.setValue(100)
        self.inten_label = QLabel("100 %")
        self.inten_label.setMinimumWidth(theme.px(56))
        irow = QHBoxLayout()
        irow.addWidget(QLabel("Más suave"))
        irow.addWidget(self.inten, 1)
        irow.addWidget(QLabel("Más intenso"))
        irow.addSpacing(12)
        irow.addWidget(self.inten_label)
        g.addWidget(QLabel("Intensidad del color:"), 2, 0)
        g.addLayout(irow, 2, 1)
        g.setColumnStretch(1, 1)
        pl.addLayout(g)
        self.crop = QCheckBox("Recortar el espacio vacío alrededor")
        self.crop.setChecked(True)
        pl.addWidget(self.crop)
        hint = QLabel("Si se borra una parte de la firma o del sello, sube la sensibilidad. "
                      "Si quedan manchas del papel, bájala. Revisa siempre con «Fondo oscuro».")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        pl.addWidget(hint)
        body.addWidget(self.panel)

        self.step3 = StepHeader(3, "Guardar")
        body.addWidget(self.step3)
        self.save_panel = QFrame()
        self.save_panel.setObjectName("Panel")
        sl = QVBoxLayout(self.save_panel)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(10)
        row = QHBoxLayout()
        self.save_btn = icon_button("Guardar PNG sin fondo", "save", "Primary")
        self.save_btn.clicked.connect(self.save_png)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        sl.addLayout(row)
        lib = QLabel("Guardar en «Mis firmas» para usarla en Editar PDF")
        lib.setObjectName("SectionTitle")
        sl.addWidget(lib)
        lrow = QHBoxLayout()
        lrow.addWidget(QLabel("Nombre:"))
        self.lib_name = QLineEdit()
        self.lib_name.setPlaceholderText("Por ejemplo: Firma Alex, Sello Mesa de Partes")
        lrow.addWidget(self.lib_name, 1)
        lrow.addWidget(QLabel("Ancho real:"))
        self.lib_width = QDoubleSpinBox()
        self.lib_width.setRange(0.5, 25)
        self.lib_width.setDecimals(1)
        self.lib_width.setSingleStep(0.1)
        self.lib_width.setValue(4.0)
        self.lib_width.setSuffix(" cm")
        lrow.addWidget(self.lib_width)
        self.lib_btn = icon_button("Guardar en Mis firmas", "signature")
        self.lib_btn.clicked.connect(self.save_library)
        lrow.addWidget(self.lib_btn)
        sl.addLayout(lrow)
        body.addWidget(self.save_panel)
        self.result = ResultPanel()
        self.result.againRequested.connect(self.reset)
        body.addWidget(self.result)
        self.error = ErrorPanel()
        body.addWidget(self.error)
        body.addStretch(1)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self.update_preview)
        self.sens.valueChanged.connect(lambda *_: self.timer.start())
        self.inten.valueChanged.connect(self._inten_changed)
        self.color.currentIndexChanged.connect(lambda *_: self.timer.start())
        self.crop.toggled.connect(lambda *_: self.timer.start())
        self._set_enabled(False)

    def _set_enabled(self, on):
        for w in (self.step2, self.panel, self.step3, self.save_panel):
            w.setVisible(on)

    def _inten_changed(self, v):
        self.inten_label.setText(f"{v} %")
        self.timer.start()

    def opts(self):
        return dict(sensitivity=self.sens.value(), color=self.color.currentData(), intensity=self.inten.value(),
                    crop=self.crop.isChecked())

    def load(self, path):
        try:
            rgb = bgremove.load_rgb(path)
        except Exception as e:
            inform(self, "No se pudo abrir", f"No se pudo leer la imagen: {e}", error=True)
            return
        self.path = path
        h, w = rgb.shape[:2]
        f = min(1.0, 900.0 / max(h, w))
        self.small = cv2.resize(rgb, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA) if f < 1 else rgb
        self.before.set_image(_to_qimage(self.small))
        self.drop.hide()
        self.chip.set_file(path, f"Imagen de {w} × {h} píxeles")
        self.chip.show()
        stem = os.path.splitext(os.path.basename(path))[0]
        self.lib_name.setText(stem[:40])
        self.result.hide()
        self.error.hide()
        self._set_enabled(True)
        self.update_preview()

    def update_preview(self):
        if self.small is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.result_small = bgremove.remove_background(self.small, **self.opts())
            self.after.set_image(_to_qimage(self.result_small))
        except Exception as e:
            self.error.show_error(f"No se pudo procesar la imagen: {e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _full(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return bgremove.process_file(self.path, max_side=2600, **self.opts())
        finally:
            QApplication.restoreOverrideCursor()

    def save_png(self):
        if not self.path:
            return
        self.error.hide()
        out = choose_output(self, self.path, "sin fondo", ".png", "Imagen PNG (*.png)")
        if not out:
            return
        try:
            bgremove.save_png(self._full(), out)
        except PermissionError:
            self.error.show_error("No se pudo guardar. Puede que el archivo esté abierto en otro programa.")
            return
        except Exception as e:
            self.error.show_error(f"No se pudo guardar: {e}")
            return
        self.result.show_result(out, f"Se guardó la imagen sin fondo: {os.path.basename(out)}\n"
                                     "Puedes insertarla en Word, Excel o en Editar PDF › Firma o sello.")
        QTimer.singleShot(60, lambda: self.scroll.ensureWidgetVisible(self.result, 0, 40))
        if settings().get("open_when_done"):
            open_path(out)

    def save_library(self):
        if not self.path:
            return
        name = self.lib_name.text().strip() or "Firma"
        try:
            dst = ec.save_signature_rgba(self._full(), name, self.lib_width.value())
        except Exception as e:
            self.error.show_error(f"No se pudo guardar en Mis firmas: {e}")
            return
        self.result.show_result("", f"Se guardó «{os.path.splitext(os.path.basename(dst))[0]}» en Mis firmas, "
                                    f"con un ancho de {self.lib_width.value():.1f} cm.\n"
                                    "Úsala en Editar PDF › Firma o sello.", title="Guardada en Mis firmas")
        QTimer.singleShot(60, lambda: self.scroll.ensureWidgetVisible(self.result, 0, 40))

    def reset(self):
        self.path = ""
        self.small = None
        self.result.hide()
        self.error.hide()
        self.chip.hide()
        self.drop.show()
        self.before.set_image(None)
        self.after.set_image(None)
        self._set_enabled(False)
