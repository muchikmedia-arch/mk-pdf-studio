"""Organizar páginas: mover, quitar, girar, agregar y extraer páginas con miniaturas."""
import os

import pymupdf
from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTransform
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QLabel, QListView,
                               QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from .widgets import (Banner, DropZone, ErrorPanel, ResultPanel, choose_output, icon_button, inform)
from ..config import settings
from ..core.common import is_signed, open_pdf
from ..core.tools import assemble

THUMB_SIZES = [110, 150, 200, 260]


class PageGrid(QListWidget):
    """Cuadrícula de páginas que se reordenan arrastrándolas con el mouse."""
    dropped = Signal(list, int)   # filas movidas, posición donde se insertan

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setFlow(QListView.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setAutoScroll(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setUniformItemSizes(False)
        self.setSpacing(10)
        self.setTextElideMode(Qt.ElideMiddle)
        self._drop_at = None

    def insert_index_at(self, pos: QPoint) -> int:
        """Posición de inserción (0..n) según dónde está el mouse, en orden de lectura."""
        n = self.count()
        for i in range(n):
            r = self.visualItemRect(self.item(i))
            if pos.y() < r.top():
                return i
            if r.top() <= pos.y() <= r.bottom() and pos.x() < r.center().x():
                return i
        return n

    def _internal(self, e):
        return e.source() is self or (e.source() is None and e.mimeData().hasFormat(
            "application/x-qabstractitemmodeldatalist"))

    def dragEnterEvent(self, e):
        if self._internal(e):
            e.setDropAction(Qt.MoveAction)
            e.accept()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if not self._internal(e):
            e.ignore()
            return
        super().dragMoveEvent(e)          # desplazamiento automático cerca de los bordes
        self._drop_at = self.insert_index_at(e.position().toPoint())
        self.viewport().update()
        e.setDropAction(Qt.MoveAction)
        e.accept()

    def dragLeaveEvent(self, e):
        self._drop_at = None
        self.viewport().update()
        super().dragLeaveEvent(e)

    def dropEvent(self, e):
        if not self._internal(e):
            e.ignore()
            return
        at = self.insert_index_at(e.position().toPoint())
        rows = sorted(self.row(it) for it in self.selectedItems())
        self._drop_at = None
        self.viewport().update()
        # Se informa la acción como "ignorada" para que Qt no borre nada por su cuenta
        e.setDropAction(Qt.IgnoreAction)
        e.accept()
        if rows:
            QTimer.singleShot(0, lambda: self.dropped.emit(rows, at))

    def paintEvent(self, e):
        super().paintEvent(e)
        if self._drop_at is None or self.count() == 0:
            return
        if self._drop_at < self.count():
            r = self.visualItemRect(self.item(self._drop_at))
            x = r.left() - 6
        else:
            r = self.visualItemRect(self.item(self.count() - 1))
            x = r.right() + 6
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.colors()["accent"]), 4, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(x, r.top() + 4, x, r.bottom() - 4)
        p.end()


class OrganizeTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.sources = {}      # id -> Document
        self.main_path = ""
        self.undo_stack = []
        self.thumb_cache = {}
        self.size_idx = 1
        self._pending = []
        self._next_id = 0

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(10)

        # --- vista inicial ---
        self.start_view = QWidget()
        sl = QVBoxLayout(self.start_view)
        sl.setContentsMargins(0, 0, 0, 0)
        t = QLabel("Organizar páginas")
        t.setObjectName("PageTitle")
        sl.addWidget(t)
        s = QLabel("Cambia el orden de las páginas arrastrándolas, quita las que no necesitas, gíralas o "
                   "agrega páginas de otro PDF. Tu archivo original no se modifica.")
        s.setObjectName("Muted")
        s.setWordWrap(True)
        sl.addWidget(s)
        self.drop = DropZone("pdf", False, "Arrastra aquí el PDF que quieres ordenar")
        self.drop.filesChosen.connect(lambda f: self.load(f[0]))
        self.drop.setMinimumHeight(theme.px(220))
        sl.addSpacing(10)
        sl.addWidget(self.drop)
        sl.addStretch(1)
        lay.addWidget(self.start_view)

        # --- editor ---
        self.editor = QWidget()
        el = QVBoxLayout(self.editor)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(10)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("SectionTitle")
        top.addWidget(self.title, 1)
        self.save_btn = icon_button("Guardar PDF", "save", "Primary")
        self.save_btn.clicked.connect(self.save)
        top.addWidget(self.save_btn)
        self.exit_btn = icon_button("Salir", "exit", tooltip="Terminar y volver al inicio de esta sección")
        self.exit_btn.clicked.connect(self.exit_doc)
        top.addWidget(self.exit_btn)
        el.addLayout(top)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.b_left = icon_button("Antes", "back", tooltip="Mover la página elegida un lugar antes")
        self.b_right = icon_button("Después", "fwd", tooltip="Mover la página elegida un lugar después")
        self.b_rotl = icon_button("Girar", "rotl", tooltip="Girar a la izquierda")
        self.b_rotr = icon_button("Girar", "rotr", tooltip="Girar a la derecha")
        self.b_del = icon_button("Quitar", "trash", tooltip="Quitar las páginas seleccionadas (tecla Supr)")
        self.b_add = icon_button("Agregar páginas", "plus", tooltip="Agregar páginas de otro PDF o de fotos")
        self.b_blank = icon_button("Hoja en blanco", "blank")
        self.b_extract = icon_button("Extraer", "extract", tooltip="Guardar solo las páginas seleccionadas en un PDF nuevo")
        self.b_undo = icon_button("Deshacer", "undo", tooltip="Deshacer (Ctrl+Z)")
        for b in (self.b_left, self.b_right, self.b_rotl, self.b_rotr, self.b_del, self.b_add, self.b_blank,
                  self.b_extract, self.b_undo):
            bar.addWidget(b)
        bar.addStretch(1)
        self.b_small = icon_button("", "zoomout", tooltip="Miniaturas más pequeñas")
        self.b_big = icon_button("", "zoomin", tooltip="Miniaturas más grandes")
        top.insertWidget(1, self.b_small)
        top.insertWidget(2, self.b_big)
        el.addLayout(bar)
        self.hint = QLabel("Arrastra las páginas para cambiarlas de lugar. Haz clic para elegir una página; "
                           "con Ctrl o Mayús puedes elegir varias.")
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        el.addWidget(self.hint)
        self.banner = Banner()
        el.addWidget(self.banner)
        self.grid = PageGrid()
        self.grid.dropped.connect(self.drop_rows)
        self.grid.itemSelectionChanged.connect(self._update_buttons)
        el.addWidget(self.grid, 1)
        self.result = ResultPanel()
        self.result.again_btn.setText("Seguir editando")
        self.result.againRequested.connect(self.result.hide)
        el.addWidget(self.result)
        self.error = ErrorPanel()
        el.addWidget(self.error)
        self.editor.hide()
        lay.addWidget(self.editor, 1)

        self.b_left.clicked.connect(lambda: self.move_selected(-1))
        self.b_right.clicked.connect(lambda: self.move_selected(1))
        self.b_rotl.clicked.connect(lambda: self.rotate(-90))
        self.b_rotr.clicked.connect(lambda: self.rotate(90))
        self.b_del.clicked.connect(self.delete)
        self.b_add.clicked.connect(self.add_pages)
        self.b_blank.clicked.connect(self.add_blank)
        self.b_extract.clicked.connect(self.extract)
        self.b_undo.clicked.connect(self.undo)
        self.b_small.clicked.connect(lambda: self.set_thumb(-1))
        self.b_big.clicked.connect(lambda: self.set_thumb(1))
        QShortcut(QKeySequence.Delete, self.grid, activated=self.delete)
        QShortcut(QKeySequence.Undo, self, activated=self.undo)

        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._render_some)
        self._apply_thumb_size()

    # ------------------------------------------------------------------
    def load(self, path):
        try:
            doc = open_pdf(path)
        except Exception as e:
            inform(self, "No se pudo abrir", str(e), error=True)
            return
        self.close_doc(silent=True)
        sid = self._add_source(doc)
        self.main_path = path
        self.title.setText(f"{os.path.basename(path)}  ·  {doc.page_count} páginas")
        entries = [{"src": sid, "page": i, "rotate": 0} for i in range(doc.page_count)]
        self._set_entries(entries)
        self.undo_stack = []
        self._saved = self.entries()
        self.start_view.hide()
        self.editor.show()
        self.result.hide()
        self.error.hide()
        if is_signed(doc) and settings().get("confirm_signed"):
            self.banner.show_text("Este PDF tiene firma digital. Si cambias sus páginas, en la copia nueva "
                                  "la firma aparecerá como no válida. Tu original no se toca.")
        else:
            self.banner.hide()
        self._update_buttons()

    def _add_source(self, doc):
        sid = self._next_id
        self._next_id += 1
        self.sources[sid] = doc
        return sid

    def has_unsaved(self):
        return bool(self.sources) and self.grid.count() > 0 and self.entries() != getattr(self, "_saved", None)

    def exit_doc(self):
        from .widgets import ask
        if self.has_unsaved() and not ask(self, "Cambios sin guardar",
                                          "Hiciste cambios que todavía no guardaste. ¿Quieres salir sin guardar?",
                                          "Salir sin guardar", "Volver"):
            return
        self.close_doc()

    def close_doc(self, silent=False):
        self.timer.stop()
        self.grid.clear()
        for d in self.sources.values():
            try:
                d.close()
            except Exception:
                pass
        self.sources = {}
        self.thumb_cache = {}
        self.undo_stack = []
        self.main_path = ""
        if not silent:
            self.editor.hide()
            self.start_view.show()

    # ------------------------------------------------------------------
    def entries(self):
        return [dict(self.grid.item(i).data(Qt.UserRole)) for i in range(self.grid.count())]

    def _placeholder(self):
        s = theme.px(THUMB_SIZES[self.size_idx])
        pm = QPixmap(s, int(s * 1.42))
        pm.fill(QColor(theme.colors()["surface2"]))
        return QIcon(pm)

    def _set_entries(self, entries, select=None):
        self.grid.clear()
        ph = self._placeholder()
        for e in entries:
            it = QListWidgetItem()
            it.setIcon(ph)
            it.setData(Qt.UserRole, dict(e))
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            self.grid.addItem(it)
        self._renumber()
        self._queue_all()
        if select:
            for r in select:
                if 0 <= r < self.grid.count():
                    self.grid.item(r).setSelected(True)
            if select and 0 <= select[0] < self.grid.count():
                self.grid.scrollToItem(self.grid.item(select[0]))
        self._last = self.entries()
        self._update_buttons()

    def _push_undo(self):
        self.undo_stack.append(self._last)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def _renumber(self):
        n = self.grid.count()
        for i in range(n):
            it = self.grid.item(i)
            e = it.data(Qt.UserRole)
            it.setText(f"{i + 1}")
            if e.get("blank"):
                it.setToolTip("Hoja en blanco")
            else:
                src_name = "" if e["src"] == 0 else " (agregada)"
                it.setToolTip(f"Página original {e['page'] + 1}{src_name}")
        if self.main_path:
            self.title.setText(f"{os.path.basename(self.main_path)}  ·  {n} páginas")

    def _after_move(self, *args):
        self._push_undo()
        self._renumber()
        self._last = self.entries()

    def selected_rows(self):
        return sorted(self.grid.row(it) for it in self.grid.selectedItems())

    def _update_buttons(self):
        has = bool(self.selected_rows())
        for b in (self.b_left, self.b_right, self.b_rotl, self.b_rotr, self.b_del, self.b_extract):
            b.setEnabled(has)
        self.b_undo.setEnabled(bool(self.undo_stack))
        self.save_btn.setEnabled(self.grid.count() > 0)

    # ------------------------------------------------------------------
    # Miniaturas
    # ------------------------------------------------------------------
    def _apply_thumb_size(self):
        s = theme.px(THUMB_SIZES[self.size_idx])
        self.grid.setIconSize(QSize(s, int(s * 1.42)))
        self.grid.setGridSize(QSize(s + 26, int(s * 1.42) + theme.px(44)))

    def set_thumb(self, d):
        self.size_idx = max(0, min(len(THUMB_SIZES) - 1, self.size_idx + d))
        self._apply_thumb_size()
        self._set_entries(self.entries(), select=self.selected_rows())

    def _queue_all(self):
        self._pending = list(range(self.grid.count()))
        if self._pending:
            self.timer.start()

    def _thumb(self, e):
        s = theme.px(THUMB_SIZES[self.size_idx])
        dpr = max(1.0, self.devicePixelRatioF())
        key = (e.get("src"), e.get("page"), e.get("rotate", 0), tuple(e.get("blank") or ()), s, dpr)
        if key in self.thumb_cache:
            return self.thumb_cache[key]
        box_w, box_h = s, int(s * 1.42)
        if e.get("blank"):
            w, h = e["blank"]
            if e.get("rotate", 0) % 180:
                w, h = h, w
            k = min(box_w / w, box_h / h)
            img = QPixmap(int(w * k * dpr), int(h * k * dpr))
            img.fill(QColor("white"))
        else:
            page = self.sources[e["src"]][e["page"]]
            r = page.rect
            rot = e.get("rotate", 0) % 360
            vw, vh = (r.height, r.width) if rot % 180 else (r.width, r.height)
            k = min(box_w / vw, box_h / vh) * dpr
            pix = page.get_pixmap(matrix=pymupdf.Matrix(k, k).prerotate(rot), alpha=False)
            img = QPixmap()
            img.loadFromData(pix.tobytes("ppm"))
        p = QPainter(img)
        p.setPen(QColor("#9AA3B2"))
        p.drawRect(0, 0, img.width() - 1, img.height() - 1)
        p.end()
        img.setDevicePixelRatio(dpr)
        self.thumb_cache[key] = img
        return img

    def _render_some(self):
        done = 0
        while self._pending and done < 3:
            row = self._pending.pop(0)
            if row >= self.grid.count():
                continue
            it = self.grid.item(row)
            try:
                it.setIcon(QIcon(self._thumb(it.data(Qt.UserRole))))
            except Exception:
                pass
            done += 1
        if not self._pending:
            self.timer.stop()

    # ------------------------------------------------------------------
    # Operaciones
    # ------------------------------------------------------------------
    def drop_rows(self, rows, at):
        """Mover las páginas arrastradas a la posición donde se soltaron."""
        ents = self.entries()
        rows = [r for r in rows if 0 <= r < len(ents)]
        if not rows:
            return
        sel = [ents[r] for r in rows]
        rest = [e for i, e in enumerate(ents) if i not in rows]
        pos = at - sum(1 for r in rows if r < at)
        pos = max(0, min(len(rest), pos))
        new = rest[:pos] + sel + rest[pos:]
        if new == ents:
            return
        self._push_undo()
        self._set_entries(new, select=list(range(pos, pos + len(sel))))

    def move_selected(self, d):
        rows = self.selected_rows()
        if not rows:
            return
        ents = self.entries()
        if d < 0 and rows[0] == 0 or d > 0 and rows[-1] == len(ents) - 1:
            return
        self._push_undo()
        sel = [ents[r] for r in rows]
        rest = [e for i, e in enumerate(ents) if i not in rows]
        pos = rows[0] + d
        pos = max(0, min(len(rest), pos))
        new = rest[:pos] + sel + rest[pos:]
        self._set_entries(new, select=list(range(pos, pos + len(sel))))

    def rotate(self, angle):
        rows = self.selected_rows()
        if not rows:
            return
        self._push_undo()
        for r in rows:
            it = self.grid.item(r)
            e = dict(it.data(Qt.UserRole))
            e["rotate"] = (e.get("rotate", 0) + angle) % 360
            it.setData(Qt.UserRole, e)
            it.setIcon(QIcon(self._thumb(e)))
        self._last = self.entries()
        self._update_buttons()

    def delete(self):
        rows = self.selected_rows()
        if not rows:
            return
        if len(rows) == self.grid.count():
            inform(self, "No se puede", "No puedes quitar todas las páginas.")
            return
        self._push_undo()
        ents = [e for i, e in enumerate(self.entries()) if i not in rows]
        self._set_entries(ents, select=[min(rows[0], len(ents) - 1)])

    def add_pages(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Agregar páginas de…", settings().get("last_dir") or "",
                                                "PDF o imágenes (*.pdf *.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if not files:
            return
        rows = self.selected_rows()
        pos = rows[-1] + 1 if rows else self.grid.count()
        self._push_undo()
        ents = self.entries()
        new = []
        for f in files:
            try:
                d = open_pdf(f)
            except Exception as e:
                inform(self, "No se pudo abrir", f"{os.path.basename(f)}: {e}", error=True)
                continue
            sid = self._add_source(d)
            new += [{"src": sid, "page": i, "rotate": 0} for i in range(d.page_count)]
        ents = ents[:pos] + new + ents[pos:]
        self._set_entries(ents, select=list(range(pos, pos + len(new))))

    def add_blank(self):
        rows = self.selected_rows()
        pos = rows[-1] + 1 if rows else self.grid.count()
        ents = self.entries()
        size = (595.28, 841.89)
        ref = ents[rows[-1]] if rows else (ents[-1] if ents else None)
        if ref and not ref.get("blank"):
            r = self.sources[ref["src"]][ref["page"]].rect
            size = (r.width, r.height)
        self._push_undo()
        ents.insert(pos, {"src": None, "page": None, "rotate": 0, "blank": size})
        self._set_entries(ents, select=[pos])

    def undo(self):
        if not self.undo_stack:
            return
        prev = self.undo_stack.pop()
        self._set_entries(prev)

    def _to_assemble(self, ents):
        out = []
        for e in ents:
            if e.get("blank"):
                out.append({"blank": e["blank"]})
            else:
                out.append({"doc": self.sources[e["src"]], "page": e["page"], "rotate": e.get("rotate", 0)})
        return out

    def save(self):
        if not self.grid.count():
            return
        out = choose_output(self, self.main_path, "ordenado", ".pdf", "PDF (*.pdf)")
        if not out:
            return
        self._do_save(self.entries(), out, "Se guardó el PDF con el nuevo orden.")

    def extract(self):
        rows = self.selected_rows()
        if not rows:
            return
        out = choose_output(self, self.main_path, "páginas extraídas", ".pdf", "PDF (*.pdf)")
        if not out:
            return
        ents = [e for i, e in enumerate(self.entries()) if i in rows]
        self._do_save(ents, out, f"Se guardaron {len(ents)} página{'s' if len(ents) != 1 else ''} en un PDF nuevo.")

    def _do_save(self, ents, out, msg):
        from PySide6.QtWidgets import QApplication
        self.error.hide()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = assemble(self._to_assemble(ents), out)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            self.error.show_error("No se pudo guardar. Puede que el archivo esté abierto en otro programa.")
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.error.show_error(f"No se pudo guardar: {e}")
            return
        QApplication.restoreOverrideCursor()
        if len(ents) == self.grid.count():
            self._saved = self.entries()
        self.result.show_result(out, f"{msg}\nTiene {r['pages']} páginas.\n\nSe guardó como: {os.path.basename(out)}")
        if settings().get("open_when_done"):
            from .widgets import open_path
            open_path(out)
