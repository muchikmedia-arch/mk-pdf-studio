"""Plantilla de página para cada herramienta: 1) archivo, 2) opciones, 3) empezar."""
import os

import pymupdf
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .widgets import (Banner, DropZone, ErrorPanel, FileChip, FileList, ProgressPanel, ResultPanel, StepHeader,
                      icon_button, inform, open_path)
from .worker import TaskRunner
from ..config import settings
from ..core.common import ext_of, human_size, is_signed, page_kind, pages_from_ranges


class ToolPage(QWidget):
    backRequested = Signal()

    title = "Herramienta"
    subtitle = ""
    icon_name = "file"
    kind = "pdf"          # pdf | images | mixed
    multi = False
    action_text = "Empezar"
    working_text = "Trabajando…"
    modifies = True       # avisar si el PDF tiene firma digital
    needs_file = True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.files = []
        self.doc_info = {}
        self.runner = TaskRunner(self)
        self.runner.progress.connect(self._on_progress)
        self.runner.finished.connect(self._on_finished)
        self.runner.failed.connect(self._on_failed)
        self.output = ""

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
        content.setMaximumWidth(900)
        center.addStretch(1)
        center.addWidget(content, 100)
        center.addStretch(1)
        self.body = QVBoxLayout(content)
        self.body.setSpacing(12)

        top = QHBoxLayout()
        back = icon_button("Volver", "back", "Flat")
        back.clicked.connect(self._back)
        top.addWidget(back)
        top.addStretch(1)
        self.body.addLayout(top)
        t = QLabel(self.title)
        t.setObjectName("PageTitle")
        t.setWordWrap(True)
        self.body.addWidget(t)
        if self.subtitle:
            s = QLabel(self.subtitle)
            s.setObjectName("Muted")
            s.setWordWrap(True)
            self.body.addWidget(s)

        step = 1
        if self.needs_file:
            self.body.addWidget(StepHeader(step, "Elige el archivo" if not self.multi else "Elige los archivos"))
            step += 1
            self.drop = DropZone(self.kind, self.multi)
            self.drop.filesChosen.connect(self.set_files)
            self.body.addWidget(self.drop)
            if self.multi:
                self.flist = FileList(self.kind)
                self.flist.add_btn.clicked.connect(self.drop.browse)
                self.flist.changed.connect(self._list_changed)
                self.flist.hide()
                self.body.addWidget(self.flist)
            else:
                self.chip = FileChip()
                self.chip.changeRequested.connect(self.drop.browse)
                self.chip.hide()
                self.body.addWidget(self.chip)
            self.banner = Banner()
            self.body.addWidget(self.banner)

        self.options_box = QFrame()
        self.options_box.setObjectName("Panel")
        ol = QVBoxLayout(self.options_box)
        ol.setContentsMargins(18, 14, 18, 14)
        ol.setSpacing(8)
        has_options = self.build_options(ol)
        if has_options:
            self.body.addWidget(StepHeader(step, "Elige cómo lo quieres"))
            step += 1
            self.body.addWidget(self.options_box)
        else:
            self.options_box.hide()

        self.body.addWidget(StepHeader(step, "Empezar"))
        row = QHBoxLayout()
        self.go = icon_button(self.action_text, "check", "Primary")
        self.go.clicked.connect(self.start)
        row.addWidget(self.go)
        row.addStretch(1)
        self.body.addLayout(row)
        self.progress = ProgressPanel()
        self.progress.cancelRequested.connect(self.cancel)
        self.body.addWidget(self.progress)
        self.result = ResultPanel()
        self.result.againRequested.connect(self.reset)
        self.body.addWidget(self.result)
        self.error = ErrorPanel()
        self.body.addWidget(self.error)
        self.body.addStretch(1)
        self._update_go()

    # ------------------------------------------------------------------
    # A implementar por cada herramienta
    # ------------------------------------------------------------------
    def build_options(self, layout) -> bool:
        return False

    def make_task(self):
        """Devuelve (ruta_funcion, args, kwargs, salida) o None si se canceló."""
        raise NotImplementedError

    def describe(self, result) -> str:
        return f"Se guardó como:\n{self.output}"

    def on_files_changed(self):
        pass

    # ------------------------------------------------------------------
    # Ayudantes para opciones
    # ------------------------------------------------------------------
    def radio_group(self, layout, options, default=0, title=None):
        if title:
            lab = QLabel(title)
            lab.setObjectName("SectionTitle")
            lab.setStyleSheet("font-size: %dpx;" % theme.px(15))
            layout.addWidget(lab)
        group = QButtonGroup(self)
        for i, (key, text) in enumerate(options):
            rb = QRadioButton(text)
            rb.setProperty("key", key)
            rb.setCursor(Qt.PointingHandCursor)
            group.addButton(rb, i)
            layout.addWidget(rb)
            if i == default:
                rb.setChecked(True)
        return group

    @staticmethod
    def group_value(group):
        b = group.checkedButton()
        return b.property("key") if b else None

    def pages_option(self, layout):
        row = QHBoxLayout()
        self._pages_group = QButtonGroup(self)
        all_rb = QRadioButton("Todas las páginas")
        some_rb = QRadioButton("Solo estas páginas:")
        all_rb.setChecked(True)
        self._pages_group.addButton(all_rb, 0)
        self._pages_group.addButton(some_rb, 1)
        self._pages_edit = QLineEdit()
        self._pages_edit.setPlaceholderText("Ejemplo: 1-3, 5, 8-10")
        self._pages_edit.setEnabled(False)
        self._pages_edit.textEdited.connect(lambda: some_rb.setChecked(True))
        some_rb.toggled.connect(self._pages_edit.setEnabled)
        row.addWidget(all_rb)
        row.addSpacing(16)
        row.addWidget(some_rb)
        row.addWidget(self._pages_edit, 1)
        layout.addLayout(row)

    def selected_pages(self):
        if not hasattr(self, "_pages_group") or self._pages_group.checkedId() == 0:
            return None
        n = self.doc_info.get("pages", 0)
        return pages_from_ranges(self._pages_edit.text(), n) or None

    # ------------------------------------------------------------------
    def _back(self):
        if self.runner.running():
            inform(self, "Trabajando", "Espera a que termine o pulsa «Cancelar».")
            return
        self.backRequested.emit()

    def set_files(self, files):
        if self.multi:
            self.flist.add_files(files)
            return
        path = files[0]
        self.files = [path]
        self.doc_info = {}
        info = ""
        try:
            size = human_size(os.path.getsize(path))
        except Exception:
            size = ""
        if ext_of(path) == ".pdf":
            try:
                doc = pymupdf.open(path)
                if doc.needs_pass:
                    self.doc_info = {"pages": 0, "locked": True}
                    info = f"PDF con contraseña · {size}"
                else:
                    n = doc.page_count
                    sample = [doc[i] for i in range(min(n, 3))]
                    kinds = [page_kind(p) for p in sample]
                    scanned = kinds.count("escaneada") > 0
                    self.doc_info = {"pages": n, "scanned": scanned, "signed": is_signed(doc)}
                    tipo = "escaneado" if scanned and kinds.count("escaneada") == len(kinds) else (
                        "con páginas escaneadas" if scanned else "digital")
                    info = f"{n} página{'s' if n != 1 else ''} · {size} · PDF {tipo}"
                doc.close()
            except Exception:
                info = f"No se pudo leer el archivo · {size}"
        else:
            info = size
            ext = ext_of(path)
            if ext in (".docx", ".doc", ".odt", ".rtf"):
                info = f"Documento de Word · {size}"
            elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"):
                info = f"Imagen · {size}"
        self.drop.hide()
        self.chip.set_file(path, info)
        self.chip.show()
        self.banner.hide()
        if self.doc_info.get("locked") and self.__class__.__name__ != "PasswordPage":
            self.banner.show_text("Este PDF tiene contraseña. Primero quítala en Herramientas › Contraseña.")
        elif self.modifies and self.doc_info.get("signed") and settings().get("confirm_signed"):
            self.banner.show_text("Este PDF tiene firma digital (por ejemplo ReFirma o Firma Perú). "
                                  "Tu archivo original no se toca, pero en la copia nueva la firma "
                                  "aparecerá como no válida.")
        self.result.hide()
        self.error.hide()
        self.on_files_changed()
        self._update_go()

    def _list_changed(self):
        self.files = self.flist.files()
        self.drop.setVisible(not self.files)
        self.flist.setVisible(bool(self.files))
        self.result.hide()
        self.error.hide()
        self.on_files_changed()
        self._update_go()

    def _update_go(self):
        ok = (not self.needs_file) or bool(self.files)
        if self.doc_info.get("locked") and self.__class__.__name__ != "PasswordPage":
            ok = False
        self.go.setEnabled(ok and not self.runner.running())

    def start(self):
        self.error.hide()
        self.result.hide()
        try:
            task = self.make_task()
        except Exception as e:
            self.error.show_error(str(e))
            return
        if not task:
            return
        func, args, kwargs, out = task
        self.output = out
        self.go.setEnabled(False)
        self.progress.start(self.working_text)
        self.runner.start(func, *args, **kwargs)
        self._reveal(self.progress)

    def cancel(self):
        self.runner.cancel()
        self.progress.hide()
        self._update_go()
        self.error.show_error("Se canceló. No se guardó ningún archivo nuevo.")
        if self.output and os.path.isfile(self.output):
            try:
                os.remove(self.output)
            except Exception:
                pass

    def _on_progress(self, frac, msg):
        self.progress.update(frac, msg)

    def _on_finished(self, result):
        self.progress.hide()
        self._update_go()
        try:
            detail = self.describe(result)
        except Exception:
            detail = f"Se guardó como:\n{self.output}"
        self.result.show_result(self.output, detail)
        self._reveal(self.result)
        if self.output and settings().get("open_when_done") and os.path.exists(self.output):
            open_path(self.output)

    def _reveal(self, widget):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(60, lambda: self.scroll.ensureWidgetVisible(widget, 0, 40))

    def _on_failed(self, msg, tb):
        self.progress.hide()
        self._update_go()
        self.error.show_error(msg)
        self._reveal(self.error)
        if tb:
            try:
                from ..config import user_data_dir
                with open(os.path.join(user_data_dir(), "errores.log"), "a", encoding="utf-8") as f:
                    f.write(tb + "\n")
            except Exception:
                pass

    def reset(self):
        self.files = []
        self.doc_info = {}
        self.result.hide()
        self.error.hide()
        if self.needs_file:
            if self.multi:
                self.flist.clear()
            else:
                self.chip.hide()
            self.drop.show()
            self.banner.hide()
        self.on_files_changed()
        self._update_go()
