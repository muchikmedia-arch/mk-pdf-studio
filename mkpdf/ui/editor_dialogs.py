"""Ventanas del editor: corregir texto, firmas guardadas y sello."""
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget)

from . import theme
from .editor_items import StampBox
from .widgets import inform
from ..config import settings
from ..core import editor_core as ec

STAMP_COLORS = {"azul": "#1A3FB0", "rojo": "#C62828", "verde": "#1E7A43", "negro": "#222222"}


def _buttons(dlg, ok_text="Aceptar"):
    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton("Cancelar")
    cancel.clicked.connect(dlg.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName("Primary")
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row, ok


def _muted(text):
    l = QLabel(text)
    l.setObjectName("Muted")
    l.setWordWrap(True)
    return l


class FixTextDialog(QDialog):
    def __init__(self, seg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Corregir texto")
        self.setMinimumWidth(theme.px(620))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        t = QLabel("Corregir texto")
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        lay.addWidget(_muted("Escribe el texto corregido. Se mantiene la misma letra, tamaño y color del documento."))
        self.edit = QLineEdit(seg["text"])
        self.edit.setMinimumHeight(theme.px(44))
        f = self.edit.font()
        f.setPixelSize(theme.px(18))
        self.edit.setFont(f)
        self.edit.selectAll()
        lay.addWidget(self.edit)
        fam, bold, _ = ec.guess_family(seg["font"])
        row = QHBoxLayout()
        self.size = QSpinBox()
        self.size.setRange(4, 96)
        self.size.setValue(int(round(seg["size"])))
        self.bold = QCheckBox("Negrita")
        self.bold.setChecked(bold or bool(seg["flags"] & 16))
        self.family = QComboBox()
        self.family.addItems(ec.EDITOR_FONTS)
        self.family.setCurrentText(fam)
        row.addWidget(QLabel("Letra:"))
        row.addWidget(self.family)
        row.addWidget(QLabel("Tamaño:"))
        row.addWidget(self.size)
        row.addWidget(self.bold)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(_muted("Si el texto nuevo es mucho más largo, puede chocar con lo que está al costado. "
                             "Para cambios grandes conviene convertir a Word."))
        b, ok = _buttons(self, "Aplicar corrección")
        lay.addLayout(b)
        self.orig_size = seg["size"]

    def values(self):
        size = self.size.value()
        if abs(size - round(self.orig_size)) < 0.01:
            size = self.orig_size
        return self.edit.text(), self.family.currentText(), size, self.bold.isChecked()


class NoteDialog(QDialog):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nota")
        self.setMinimumWidth(theme.px(480))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        t = QLabel("Escribe tu nota")
        t.setObjectName("SectionTitle")
        lay.addWidget(t)
        lay.addWidget(_muted("La nota aparece como un papelito amarillo. Al pasar el mouse se lee el texto."))
        self.edit = QPlainTextEdit(text)
        self.edit.setMinimumHeight(theme.px(140))
        lay.addWidget(self.edit)
        b, ok = _buttons(self, "Guardar nota")
        lay.addLayout(b)

    def text(self):
        return self.edit.toPlainText().strip()


class SignatureDialog(QDialog):
    """Biblioteca de firmas y sellos (imágenes) guardados en la computadora."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Firma o sello")
        self.setMinimumSize(QSize(theme.px(640), theme.px(520)))
        self.chosen = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        t = QLabel("Elige una firma o sello")
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        lay.addWidget(_muted("Guarda aquí la imagen escaneada o la foto de tu firma o de un sello. "
                             "Se guarda en esta computadora para usarla cuando quieras."))
        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(QSize(theme.px(170), theme.px(90)))
        self.list.setGridSize(QSize(theme.px(200), theme.px(140)))
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda *_: self._use())
        lay.addWidget(self.list, 1)
        self.empty = _muted("Todavía no hay firmas guardadas. Pulsa «Agregar desde una imagen».")
        lay.addWidget(self.empty)
        row = QHBoxLayout()
        add = QPushButton("Agregar desde una imagen…")
        add.clicked.connect(self._add)
        self.white = QCheckBox("Quitar el fondo blanco")
        self.white.setChecked(True)
        delete = QPushButton("Borrar")
        delete.setObjectName("Danger")
        delete.clicked.connect(self._delete)
        row.addWidget(add)
        row.addWidget(self.white)
        row.addStretch(1)
        row.addWidget(delete)
        lay.addLayout(row)
        b, self.ok = _buttons(self, "Poner en el documento")
        self.ok.clicked.disconnect()
        self.ok.clicked.connect(self._use)
        lay.addLayout(b)
        self._load()

    def _load(self):
        self.list.clear()
        for path in ec.list_signatures():
            pm = QPixmap(path)
            if pm.isNull():
                continue
            box = QPixmap(theme.px(170), theme.px(90))
            box.fill(QColor("white"))
            p = QPainter(box)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            scaled = pm.scaled(box.size() * 0.92, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap((box.width() - scaled.width()) // 2, (box.height() - scaled.height()) // 2, scaled)
            p.setPen(QColor("#C9D1DD"))
            p.drawRect(0, 0, box.width() - 1, box.height() - 1)
            p.end()
            it = QListWidgetItem(QIcon(box), os.path.splitext(os.path.basename(path))[0])
            it.setData(Qt.UserRole, path)
            self.list.addItem(it)
        self.empty.setVisible(self.list.count() == 0)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _add(self):
        f, _ = QFileDialog.getOpenFileName(self, "Imagen de la firma o sello", settings().get("last_dir") or "",
                                           "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not f:
            return
        try:
            ec.import_signature(f, remove_white=self.white.isChecked())
        except Exception as e:
            inform(self, "No se pudo agregar", f"No se pudo leer la imagen: {e}", error=True)
            return
        self._load()

    def _delete(self):
        it = self.list.currentItem()
        if not it:
            return
        from .widgets import ask
        if ask(self, "Borrar", "¿Borrar esta firma o sello de la biblioteca?", "Borrar", "Cancelar"):
            try:
                os.remove(it.data(Qt.UserRole))
            except Exception:
                pass
            self._load()

    def _use(self):
        it = self.list.currentItem()
        if not it:
            inform(self, "Elige una firma", "Primero agrega o elige una firma o sello.")
            return
        self.chosen = it.data(Qt.UserRole)
        self.accept()


class StampPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(QSize(theme.px(300), theme.px(140)))
        self.title, self.lines, self.color = "RECIBIDO", [], QColor("#1A3FB0")

    def set_data(self, title, lines, color):
        self.title, self.lines, self.color = title, lines, QColor(color)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("white"))
        w, h = stamp_size(self.lines)
        k = min((self.width() - 20) / w, (self.height() - 20) / h)
        item = StampBox(self.title, self.lines, self.color, w, h)
        p.translate((self.width() - w * k) / 2, (self.height() - h * k) / 2)
        p.scale(k, k)
        item.paint(p, None, None)
        p.end()


def stamp_size(lines):
    w = 190.0
    h = 34.0 + 14.5 * len([l for l in lines if l is not None])
    return w, h


class StampDialog(QDialog):
    TITLES = ["RECIBIDO", "ATENDIDO", "ARCHIVADO", "COPIA FIEL DEL ORIGINAL", "VISTO BUENO", "URGENTE",
              "PROVEÍDO", "ANULADO"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sello")
        self.setMinimumWidth(theme.px(560))
        st = settings()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        t = QLabel("Sello con fecha y hora")
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        self.title = QComboBox()
        self.title.setEditable(True)
        self.title.addItems(self.TITLES)
        self.title.setCurrentText(st.get("stamp_title") or "RECIBIDO")
        self.area = QLineEdit(st.get("stamp_area") or "")
        self.area.setPlaceholderText("Por ejemplo: Mesa de Partes – Municipalidad Distrital")
        self.color = QComboBox()
        for k in STAMP_COLORS:
            self.color.addItem(k.capitalize(), k)
        idx = list(STAMP_COLORS).index(st.get("stamp_color")) if st.get("stamp_color") in STAMP_COLORS else 0
        self.color.setCurrentIndex(idx)
        g.addWidget(QLabel("Texto principal:"), 0, 0)
        g.addWidget(self.title, 0, 1)
        g.addWidget(QLabel("Oficina o institución:"), 1, 0)
        g.addWidget(self.area, 1, 1)
        g.addWidget(QLabel("Color:"), 2, 0)
        g.addWidget(self.color, 2, 1)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        self.date = QCheckBox("Poner la fecha y la hora de ahora")
        self.date.setChecked(bool(st.get("stamp_date")))
        self.fields = QCheckBox("Agregar espacios para «Folios» y «Firma»")
        self.fields.setChecked(bool(st.get("stamp_fields")))
        lay.addWidget(self.date)
        lay.addWidget(self.fields)
        self.preview = StampPreview()
        lay.addWidget(self.preview)
        b, ok = _buttons(self, "Poner sello")
        lay.addLayout(b)
        for w in (self.title, self.color):
            w.currentTextChanged.connect(self._update)
        self.area.textChanged.connect(self._update)
        self.date.toggled.connect(self._update)
        self.fields.toggled.connect(self._update)
        self._update()

    def data(self):
        lines = ec.default_stamp_lines(self.area.text().strip(), self.date.isChecked(), self.fields.isChecked())
        return self.title.currentText().strip() or "RECIBIDO", lines, STAMP_COLORS[self.color.currentData()]

    def _update(self, *a):
        self.preview.set_data(*self.data())

    def accept(self):
        st = settings()
        st.data.update({"stamp_title": self.title.currentText().strip(), "stamp_area": self.area.text().strip(),
                        "stamp_color": self.color.currentData(), "stamp_date": self.date.isChecked(),
                        "stamp_fields": self.fields.isChecked()})
        st.save()
        super().accept()
