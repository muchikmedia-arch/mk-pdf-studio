"""Componentes visuales reutilizables."""
import os
import subprocess
import sys

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMessageBox, QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import icons, theme
from ..config import settings
from ..core.common import EXCEL_EXT, IMAGE_EXT, PDF_EXT, WORD_EXT, ext_of, human_size, output_path, unique_path


def open_path(path: str):
    if not path:
        return
    if sys.platform.startswith("win"):
        try:
            os.startfile(path)  # noqa
            return
        except Exception:
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def show_in_folder(path: str):
    if sys.platform.startswith("win") and os.path.isfile(path):
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return
        except Exception:
            pass
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def choose_output(parent, src: str, suffix: str, ext: str, filter_text: str) -> str:
    """Decide dónde guardar según los Ajustes. Devuelve '' si el usuario cancela."""
    st = settings()
    mode = st.get("save_mode")
    if mode == "carpeta" and st.get("save_folder") and os.path.isdir(st.get("save_folder")):
        return output_path(src, suffix, ext, st.get("save_folder"))
    default = output_path(src, suffix, ext)
    if mode == "preguntar":
        path, _ = QFileDialog.getSaveFileName(parent, "Guardar como", default, filter_text)
        if not path:
            return ""
        if not path.lower().endswith(ext):
            path += ext
        return path
    return default


def output_folder(parent, src: str) -> str:
    st = settings()
    mode = st.get("save_mode")
    if mode == "carpeta" and st.get("save_folder") and os.path.isdir(st.get("save_folder")):
        return st.get("save_folder")
    if mode == "preguntar":
        return QFileDialog.getExistingDirectory(parent, "Elige la carpeta donde guardar",
                                                os.path.dirname(src)) or ""
    return os.path.dirname(os.path.abspath(src))


def ask(parent, title, text, yes="Sí", no="No") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Question)
    by = box.addButton(yes, QMessageBox.YesRole)
    box.addButton(no, QMessageBox.NoRole)
    box.exec()
    return box.clickedButton() is by


def inform(parent, title, text, error=False):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Warning if error else QMessageBox.Information)
    box.addButton("Aceptar", QMessageBox.AcceptRole)
    box.exec()


class IconLabel(QLabel):
    def __init__(self, name, size=28, color_key="accent", parent=None):
        super().__init__(parent)
        self.name, self.size_, self.color_key = name, size, color_key
        self.refresh()

    def refresh(self):
        self.setPixmap(icons.pixmap(self.name, theme.colors()[self.color_key], theme.px(self.size_)))


def icon_button(text, icon_name, object_name=None, tooltip=None):
    b = QPushButton(text)
    if object_name:
        b.setObjectName(object_name)
    color = theme.colors()["accent_text"] if object_name == "Primary" else theme.colors()["accent"]
    b.setIcon(icons.icon(icon_name, color))
    b.setIconSize(QSize(theme.px(20), theme.px(20)))
    b.setCursor(Qt.PointingHandCursor)
    b._icon_name = icon_name
    if tooltip:
        b.setToolTip(tooltip)
    return b


def refresh_button_icons(root: QWidget):
    c = theme.colors()
    for b in root.findChildren(QPushButton):
        name = getattr(b, "_icon_name", None)
        if name:
            color = c["accent_text"] if b.objectName() == "Primary" else c["accent"]
            if b.objectName() == "Danger":
                color = c["danger"]
            b.setIcon(icons.icon(name, color))
            b.setIconSize(QSize(theme.px(20), theme.px(20)))
    for l in root.findChildren(IconLabel):
        l.refresh()


class Card(QFrame):
    clicked = Signal()

    def __init__(self, icon_name, title, text, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(16)
        badge = QFrame()
        badge.setObjectName("IconBadge")
        bl = QVBoxLayout(badge)
        bl.setContentsMargins(10, 10, 10, 10)
        self.icon = IconLabel(icon_name, 30)
        bl.addWidget(self.icon)
        badge.setStyleSheet(f"QFrame#IconBadge {{ background: {theme.colors()['accent_soft']}; border-radius: 12px; border: none; }}")
        self.badge = badge
        lay.addWidget(badge, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        t.setWordWrap(True)
        d = QLabel(text)
        d.setObjectName("CardText")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self.setMinimumHeight(theme.px(96))

    def refresh(self):
        self.badge.setStyleSheet(f"QFrame#IconBadge {{ background: {theme.colors()['accent_soft']}; border-radius: 12px; border: none; }}")
        self.icon.refresh()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)


class StepHeader(QWidget):
    def __init__(self, number, text, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 2)
        lay.setSpacing(10)
        n = QLabel(str(number))
        n.setObjectName("StepNumber")
        t = QLabel(text)
        t.setObjectName("SectionTitle")
        lay.addWidget(n)
        lay.addWidget(t)
        lay.addStretch(1)


class Banner(QFrame):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.ic = IconLabel("warn", 22, "warn")
        lay.addWidget(self.ic, 0, Qt.AlignTop)
        self.label = QLabel(text)
        self.label.setObjectName("BannerText")
        self.label.setWordWrap(True)
        lay.addWidget(self.label, 1)
        self.hide()

    def show_text(self, text):
        self.label.setText(text)
        self.show()


def file_filter(kind: str) -> str:
    if kind == "pdf":
        return "Documentos PDF (*.pdf)"
    if kind == "images":
        return "Imágenes (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)"
    if kind == "word":
        return "Documentos de Word (*.docx *.doc *.odt *.rtf)"
    if kind == "mixed":
        return ("Archivos para unir (*.pdf *.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp *.doc *.docx *.odt *.rtf "
                "*.xls *.xlsx *.ods);;Todos los archivos (*.*)")
    return "Todos los archivos (*.*)"


def accepts(kind: str, path: str) -> bool:
    e = ext_of(path)
    if kind == "pdf":
        return e in PDF_EXT
    if kind == "images":
        return e in IMAGE_EXT
    if kind == "word":
        return e in WORD_EXT
    if kind == "mixed":
        return e in PDF_EXT + IMAGE_EXT + WORD_EXT + EXCEL_EXT
    return True


class DropZone(QFrame):
    """Zona para arrastrar archivos o hacer clic para buscarlos."""
    filesChosen = Signal(list)

    def __init__(self, kind="pdf", multi=False, text=None, parent=None):
        super().__init__(parent)
        self.kind, self.multi = kind, multi
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 26, 20, 26)
        lay.setSpacing(8)
        self.ic = IconLabel("upload", 36)
        lay.addWidget(self.ic, 0, Qt.AlignHCenter)
        what = {"pdf": "tu PDF" if not multi else "tus PDF", "images": "tus fotos o imágenes",
                "word": "tu documento de Word",
                "mixed": "los archivos (PDF, fotos, Word o Excel)"}.get(kind, "el archivo")
        t = QLabel(text or f"Arrastra aquí {what}")
        t.setObjectName("Big")
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        lay.addWidget(t)
        sub = QLabel("o haz clic para buscar en tu computadora")
        sub.setObjectName("Muted")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.browse()

    def browse(self):
        st = settings()
        start = st.get("last_dir") or os.path.expanduser("~")
        if self.multi:
            files, _ = QFileDialog.getOpenFileNames(self, "Elegir archivos", start, file_filter(self.kind))
        else:
            f, _ = QFileDialog.getOpenFileName(self, "Elegir archivo", start, file_filter(self.kind))
            files = [f] if f else []
        if files:
            st.set("last_dir", os.path.dirname(files[0]))
            self.filesChosen.emit(files)

    def _set_hover(self, on):
        self.setProperty("hover", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_hover(True)

    def dragLeaveEvent(self, e):
        self._set_hover(False)

    def dropEvent(self, e):
        self._set_hover(False)
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        good = [f for f in files if os.path.isfile(f) and accepts(self.kind, f)]
        if not good:
            inform(self, "Archivo no válido", "Ese tipo de archivo no sirve para esta herramienta.")
            return
        if not self.multi:
            good = good[:1]
        settings().set("last_dir", os.path.dirname(good[0]))
        self.filesChosen.emit(good)


class FileChip(QFrame):
    """Muestra el archivo elegido con su información."""
    changeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FileChip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(12)
        self.ic = IconLabel("file", 30)
        lay.addWidget(self.ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = QLabel()
        self.name.setObjectName("SectionTitle")
        self.name.setWordWrap(True)
        self.info = QLabel()
        self.info.setObjectName("Muted")
        col.addWidget(self.name)
        col.addWidget(self.info)
        lay.addLayout(col, 1)
        self.change = QPushButton("Cambiar archivo")
        self.change.setObjectName("Flat")
        self.change.setCursor(Qt.PointingHandCursor)
        self.change.clicked.connect(self.changeRequested)
        lay.addWidget(self.change)

    def set_file(self, path, info=""):
        self.name.setText(os.path.basename(path))
        self.info.setText(info)


class FileList(QWidget):
    """Lista de varios archivos con botones para ordenar."""
    changed = Signal()

    def __init__(self, kind="mixed", parent=None):
        super().__init__(parent)
        self.kind = kind
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.InternalMove)
        self.list.setSelectionMode(QListWidget.SingleSelection)
        self.list.setMinimumHeight(theme.px(170))
        self.list.model().rowsMoved.connect(lambda *a: self.changed.emit())
        lay.addWidget(self.list)
        row = QHBoxLayout()
        self.add_btn = icon_button("Agregar más", "plus")
        self.up_btn = icon_button("Subir", "up")
        self.down_btn = icon_button("Bajar", "down")
        self.rm_btn = icon_button("Quitar", "trash")
        for b in (self.add_btn, self.up_btn, self.down_btn, self.rm_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.rm_btn.clicked.connect(self._remove)

    def add_files(self, files):
        existing = set(self.files())
        for f in files:
            if f in existing:
                continue
            it = QListWidgetItem(os.path.basename(f))
            it.setData(Qt.UserRole, f)
            it.setToolTip(f)
            try:
                it.setText(f"{os.path.basename(f)}    ·  {human_size(os.path.getsize(f))}")
            except Exception:
                pass
            self.list.addItem(it)
        self.changed.emit()

    def files(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def clear(self):
        self.list.clear()
        self.changed.emit()

    def _move(self, d):
        r = self.list.currentRow()
        if r < 0:
            return
        nr = r + d
        if 0 <= nr < self.list.count():
            it = self.list.takeItem(r)
            self.list.insertItem(nr, it)
            self.list.setCurrentRow(nr)
            self.changed.emit()

    def _remove(self):
        r = self.list.currentRow()
        if r >= 0:
            self.list.takeItem(r)
            self.changed.emit()


class ProgressPanel(QFrame):
    cancelRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        self.msg = QLabel("Trabajando…")
        self.msg.setObjectName("Big")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.hint = QLabel("Puedes seguir usando la computadora mientras tanto.")
        self.hint.setObjectName("Muted")
        row.addWidget(self.hint, 1)
        self.cancel = QPushButton("Cancelar")
        self.cancel.setCursor(Qt.PointingHandCursor)
        self.cancel.clicked.connect(self.cancelRequested)
        row.addWidget(self.cancel)
        lay.addLayout(row)
        self.hide()

    def start(self, text):
        self.msg.setText(text)
        self.bar.setValue(0)
        self.show()

    def update(self, frac, text):
        self.bar.setValue(int(frac * 1000))
        if text:
            self.msg.setText(text)


class ResultPanel(QFrame):
    againRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Success")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(8)
        top = QHBoxLayout()
        self.ic = IconLabel("check", 28, "ok")
        top.addWidget(self.ic)
        self.title = QLabel("¡Listo!")
        self.title.setObjectName("SuccessTitle")
        top.addWidget(self.title, 1)
        lay.addLayout(top)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.detail)
        row = QHBoxLayout()
        self.open_btn = icon_button("Abrir", "open", "Primary")
        self.folder_btn = icon_button("Ver en la carpeta", "folder")
        self.again_btn = QPushButton("Hacer otro")
        self.again_btn.setObjectName("Flat")
        self.again_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.open_btn)
        row.addWidget(self.folder_btn)
        row.addStretch(1)
        row.addWidget(self.again_btn)
        lay.addLayout(row)
        self.path = ""
        self.open_btn.clicked.connect(lambda: open_path(self.path))
        self.folder_btn.clicked.connect(lambda: show_in_folder(self.path))
        self.again_btn.clicked.connect(self.againRequested)
        self.hide()

    def show_result(self, path, detail, title="¡Listo!"):
        self.path = path
        self.title.setText(title)
        self.detail.setText(detail)
        self.open_btn.setVisible(bool(path))
        self.folder_btn.setVisible(bool(path))
        self.open_btn.setText("Abrir carpeta" if path and os.path.isdir(path) else "Abrir")
        self.show()


class ErrorPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Error")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.ic = IconLabel("warn", 24, "danger")
        lay.addWidget(self.ic, 0, Qt.AlignTop)
        self.text = QLabel()
        self.text.setObjectName("ErrorText")
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.text, 1)
        self.hide()

    def show_error(self, text):
        self.text.setText(text)
        self.show()
