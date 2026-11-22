"""Pestaña «Editar PDF»: escribir, corregir, resaltar, firmar, sellar, tapar y dibujar sobre el PDF."""
import os

import pymupdf
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFrame,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import icons, theme
from .editor_dialogs import FixTextDialog, NoteDialog, SignatureDialog, StampDialog, stamp_size
from .editor_items import (ImageBox, InkItem, MarkupItem, NoteItem, Overlay, PageFrame, RectBox, StampBox,
                           TextBox, WhiteoutBox)
from .widgets import (Banner, DropZone, ErrorPanel, ResultPanel, ask, choose_output, icon_button, inform,
                      open_path)
from ..config import settings
from ..core import editor_core as ec
from ..core.common import is_signed

GAP = 16.0
PX_PER_PT_100 = 96.0 / 72.0   # 100 % = tamaño real en pantalla

TOOLS = [
    ("select", "cursor", "Seleccionar", "Haz clic en algo que agregaste para moverlo. Con la tecla Supr lo borras. "
                                        "Doble clic en un texto para modificarlo."),
    ("text", "type", "Escribir texto", "Haz clic en la página donde quieres escribir."),
    ("fix", "fixtext", "Corregir texto", "Pasa el mouse sobre el texto del documento y haz clic en el que quieres "
                                         "corregir."),
    ("highlight", "marker", "Resaltar", "Arrastra el mouse sobre el texto que quieres resaltar."),
    ("underline", "underline", "Subrayar", "Arrastra el mouse sobre el texto que quieres subrayar."),
    ("strike", "strike", "Tachar", "Arrastra el mouse sobre el texto que quieres tachar."),
    ("note", "note", "Nota", "Haz clic donde quieres dejar una nota."),
    ("whiteout", "eraser", "Tapar", "Arrastra para cubrir una parte. Al guardar, lo que está debajo se borra de "
                                    "verdad (sirve para ocultar datos)."),
    ("sign", "signature", "Firma o sello", "Elige una firma o sello guardado; luego arrástralo a su lugar."),
    ("stamp", "stamp", "Sello Recibido", "Pone un sello con la fecha y la hora."),
    ("pen", "pen", "Dibujar", "Mantén presionado el botón del mouse y dibuja."),
    ("rect", "square", "Recuadro", "Arrastra para dibujar un recuadro."),
]
TOOL_HINT = {k: h for k, _, _, h in TOOLS}
COLORS = [("#000000", "Negro"), ("#1A3FB0", "Azul"), ("#C62828", "Rojo"), ("#1E7A43", "Verde"), ("#FFE200", "Amarillo")]


class EditorView(QGraphicsView):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.viewport().setMouseTracking(True)
        self.setFrameShape(QFrame.NoFrame)
        self._press = None
        self._moved_from = None

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.editor.zoom_by(1.12 if e.angleDelta().y() > 0 else 1 / 1.12)
            e.accept()
            return
        super().wheelEvent(e)

    def keyPressEvent(self, e):
        focus = self.scene().focusItem() if self.scene() else None
        editing = isinstance(focus, TextBox) and focus.editing()
        if not editing and e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.editor.delete_selected()
            e.accept()
            return
        if not editing and e.key() == Qt.Key_Escape:
            self.editor.set_tool("select")
            return
        super().keyPressEvent(e)

    def _page_point(self, e):
        sp = self.mapToScene(e.position().toPoint())
        frame = self.editor.frame_at(sp)
        if frame is None:
            return None, None
        return frame, frame.mapFromScene(sp)

    def mousePressEvent(self, e):
        tool = self.editor.tool
        if e.button() == Qt.LeftButton and tool != "select":
            item = self.itemAt(e.position().toPoint())
            if tool == "text" and isinstance(item, TextBox):
                super().mousePressEvent(e)
                return
            frame, pp = self._page_point(e)
            if frame is not None:
                self.editor.tool_press(frame, pp)
                e.accept()
                return
        super().mousePressEvent(e)
        if tool == "select":
            self._moved_from = [(it, QPointF(it.pos())) for it in self.scene().selectedItems()]

    def mouseMoveEvent(self, e):
        tool = self.editor.tool
        if tool != "select":
            frame, pp = self._page_point(e)
            self.editor.tool_move(frame, pp, bool(e.buttons() & Qt.LeftButton))
            if e.buttons() & Qt.LeftButton:
                e.accept()
                return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        tool = self.editor.tool
        if tool != "select" and e.button() == Qt.LeftButton:
            frame, pp = self._page_point(e)
            self.editor.tool_release(frame, pp)
            e.accept()
            return
        super().mouseReleaseEvent(e)
        if tool == "select" and self._moved_from:
            moved = [(it, old) for it, old in self._moved_from if it.scene() and it.pos() != old]
            if moved:
                self.editor.push_undo(("move", moved))
            self._moved_from = None


class EditorTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.doc = None
        self.path = ""
        self.frames = []
        self.tool = "select"
        self.undo_stack = []
        self.dirty = False
        self.zoom = 1.0
        self.seg_cache = {}
        self.word_cache = {}
        self.fields = []
        self._drag = None
        self._temp = None
        self._hover = None
        self._hover_seg = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---------- vista inicial ----------
        self.start_view = QWidget()
        sl = QVBoxLayout(self.start_view)
        sl.setContentsMargins(24, 16, 24, 16)
        t = QLabel("Editar PDF")
        t.setObjectName("PageTitle")
        sl.addWidget(t)
        s = QLabel("Escribe sobre el documento, corrige una palabra o un monto, resalta, pon tu firma o el sello "
                   "de «Recibido», tapa datos o llena formularios. Tu archivo original no se modifica.")
        s.setObjectName("Muted")
        s.setWordWrap(True)
        sl.addWidget(s)
        sl.addSpacing(10)
        self.drop = DropZone("pdf", False, "Arrastra aquí el PDF que quieres editar")
        self.drop.setMinimumHeight(theme.px(220))
        self.drop.filesChosen.connect(lambda f: self.load(f[0]))
        sl.addWidget(self.drop)
        sl.addStretch(1)
        lay.addWidget(self.start_view)

        # ---------- editor ----------
        self.editor_view = QWidget()
        ev = QVBoxLayout(self.editor_view)
        ev.setContentsMargins(0, 0, 0, 0)
        ev.setSpacing(0)

        top = QWidget()
        top.setObjectName("Header")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 8, 16, 8)
        tl.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("SectionTitle")
        self.title.setMinimumWidth(80)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        tl.addWidget(self.title, 1)
        other = QPushButton("Abrir otro PDF")
        other.setObjectName("Flat")
        other.clicked.connect(self.close_doc)
        tl.addWidget(other)
        self.b_prev = icon_button("", "prev", tooltip="Página anterior")
        self.page_edit = QLineEdit("1")
        from PySide6.QtGui import QIntValidator
        self.page_edit.setValidator(QIntValidator(1, 99999, self))
        self.page_edit.setAlignment(Qt.AlignCenter)
        self.page_edit.setFixedWidth(theme.px(58))
        self.page_edit.setToolTip("Escribe el número de página y pulsa Enter")
        self.page_total = QLabel()
        self.b_next = icon_button("", "next", tooltip="Página siguiente")
        for w in (self.b_prev, self.page_edit, self.page_total, self.b_next):
            tl.addWidget(w)
        tl.addSpacing(8)
        self.b_zout = icon_button("", "zoomout", tooltip="Alejar (Ctrl + rueda del mouse)")
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setMinimumWidth(theme.px(56))
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.b_zin = icon_button("", "zoomin", tooltip="Acercar")
        self.b_fit = icon_button("", "fit", tooltip="Ajustar al ancho de la ventana")
        for w in (self.b_zout, self.zoom_label, self.b_zin, self.b_fit):
            tl.addWidget(w)
        tl.addSpacing(8)
        self.b_undo = icon_button("Deshacer", "undo", tooltip="Deshacer (Ctrl+Z)")
        tl.addWidget(self.b_undo)
        self.save_btn = icon_button("Guardar PDF", "save", "Primary")
        self.save_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        tl.addWidget(self.save_btn)
        ev.addWidget(top)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # panel de herramientas
        side = QWidget()
        side.setObjectName("Header")
        side.setFixedWidth(theme.px(206))
        sdl = QVBoxLayout(side)
        sdl.setContentsMargins(10, 10, 10, 10)
        sdl.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}
        for key, icon_name, label, _ in TOOLS:
            b = QToolButton()
            b.setText("  " + label)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setIcon(icons.icon(icon_name, theme.colors()["accent"]))
            b.setIconSize(QSize(theme.px(20), theme.px(20)))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
            b._icon_name = icon_name
            b.setObjectName("ToolButton")
            self.tool_group.addButton(b)
            self.tool_buttons[key] = b
            b.clicked.connect(lambda _=False, k=key: self.set_tool(k))
            sdl.addWidget(b)
        sdl.addSpacing(8)
        # propiedades
        self.props = QFrame()
        self.props.setObjectName("Panel")
        pl = QVBoxLayout(self.props)
        pl.setContentsMargins(10, 10, 10, 10)
        pl.setSpacing(6)
        self.prop_font = QComboBox()
        self.prop_font.addItems(ec.EDITOR_FONTS)
        self.prop_font.setCurrentText(settings().get("editor_font") or "Arial")
        self.prop_size = QSpinBox()
        self.prop_size.setRange(6, 96)
        self.prop_size.setValue(int(settings().get("editor_size") or 12))
        self.prop_size.setSuffix(" pt")
        self.prop_bold = QCheckBox("Negrita")
        self.prop_width = QComboBox()
        for w, t in ((1.0, "Fino"), (2.0, "Normal"), (3.5, "Grueso")):
            self.prop_width.addItem(t, w)
        self.prop_width.setCurrentIndex(1)
        self.font_row = QWidget()
        fr = QVBoxLayout(self.font_row)
        fr.setContentsMargins(0, 0, 0, 0)
        fr.setSpacing(6)
        fr.addWidget(QLabel("Letra"))
        fr.addWidget(self.prop_font)
        srow = QHBoxLayout()
        srow.addWidget(self.prop_size)
        srow.addWidget(self.prop_bold)
        fr.addLayout(srow)
        pl.addWidget(self.font_row)
        self.width_row = QWidget()
        wr = QVBoxLayout(self.width_row)
        wr.setContentsMargins(0, 0, 0, 0)
        wr.addWidget(QLabel("Grosor"))
        wr.addWidget(self.prop_width)
        pl.addWidget(self.width_row)
        self.color_row = QWidget()
        cr = QVBoxLayout(self.color_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.addWidget(QLabel("Color"))
        sw = QHBoxLayout()
        sw.setSpacing(4)
        self.color_group = QButtonGroup(self)
        for i, (hexc, name) in enumerate(COLORS):
            b = QPushButton()
            b.setCheckable(True)
            b.setToolTip(name)
            b.setFixedSize(theme.px(26), theme.px(26))
            b.setStyleSheet(f"QPushButton {{ background: {hexc}; border: 2px solid #C9D1DD; border-radius: {theme.px(13)}px; padding: 0; }}"
                            f"QPushButton:checked {{ border: 3px solid {theme.colors()['accent']}; }}")
            b.setProperty("hex", hexc)
            self.color_group.addButton(b, i)
            sw.addWidget(b)
        sw.addStretch(1)
        cr.addLayout(sw)
        pl.addWidget(self.color_row)
        sdl.addWidget(self.props)
        sdl.addStretch(1)
        body.addWidget(side)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(0)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setContentsMargins(16, 8, 16, 8)
        self.hint.setObjectName("HintBar")
        center.addWidget(self.hint)
        self.banner = Banner()
        center.addWidget(self.banner)
        self.result = ResultPanel()
        self.result.again_btn.setText("Seguir editando")
        self.result.againRequested.connect(self.result.hide)
        center.addWidget(self.result)
        self.error = ErrorPanel()
        center.addWidget(self.error)
        self.scene = QGraphicsScene(self)
        self.view = EditorView(self)
        self.view.setScene(self.scene)
        center.addWidget(self.view, 1)
        body.addLayout(center, 1)
        ev.addLayout(body, 1)
        self.editor_view.hide()
        lay.addWidget(self.editor_view, 1)

        # conexiones
        self.b_prev.clicked.connect(lambda: self.goto_page(self.current_page() - 1))
        self.b_next.clicked.connect(lambda: self.goto_page(self.current_page() + 1))
        self.page_edit.editingFinished.connect(
            lambda: self.goto_page(int(self.page_edit.text() or "1") - 1))
        self.b_zin.clicked.connect(lambda: self.zoom_by(1.2))
        self.b_zout.clicked.connect(lambda: self.zoom_by(1 / 1.2))
        self.b_fit.clicked.connect(self.fit_width)
        self.b_undo.clicked.connect(self.undo)
        self.save_btn.clicked.connect(self.save)
        QShortcut(QKeySequence.Undo, self, activated=self._shortcut_undo)
        QShortcut(QKeySequence.Save, self, activated=self.save)
        self.prop_font.currentTextChanged.connect(self._props_changed)
        self.prop_size.valueChanged.connect(self._props_changed)
        self.prop_bold.toggled.connect(self._props_changed)
        self.prop_width.currentIndexChanged.connect(self._props_changed)
        self.color_group.idClicked.connect(lambda *_: self._props_changed())
        self.scene.selectionChanged.connect(self._selection_changed)
        self.view.verticalScrollBar().valueChanged.connect(self._schedule_render)
        self.view.horizontalScrollBar().valueChanged.connect(self._schedule_render)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(70)
        self.render_timer.timeout.connect(self.render_visible)
        self.tool_colors = {"text": 0, "pen": 2, "rect": 2, "highlight": 4, "underline": 1, "strike": 2}
        self.set_tool("select")
        self._style_hint()

    # ------------------------------------------------------------------
    # Apariencia
    # ------------------------------------------------------------------
    def _style_hint(self):
        c = theme.colors()
        self.hint.setStyleSheet(f"QLabel#HintBar {{ background: {c['accent_soft']}; color: {c['text']};"
                                f" border-bottom: 1px solid {c['border']}; font-size: {theme.px(15)}px; }}")
        self.scene.setBackgroundBrush(QBrush(QColor(c["surface2"])))
        for b in self.tool_buttons.values():
            b.setIcon(icons.icon(b._icon_name, c["accent"]))
            b.setIconSize(QSize(theme.px(20), theme.px(20)))
            b.setStyleSheet(
                f"QToolButton {{ text-align: left; padding: {theme.px(8)}px {theme.px(10)}px; border-radius: 8px;"
                f" border: 1px solid transparent; background: transparent; font-weight: 600; }}"
                f"QToolButton:hover {{ background: {c['surface2']}; }}"
                f"QToolButton:checked {{ background: {c['accent_soft']}; border: 1px solid {c['accent']}; color: {c['accent']}; }}")

    def refresh_theme(self):
        self._style_hint()

    # ------------------------------------------------------------------
    # Abrir / cerrar
    # ------------------------------------------------------------------
    def load(self, path):
        if self.dirty and not ask(self, "Cambios sin guardar", "Hay cambios sin guardar en el documento actual. "
                                  "¿Quieres descartarlos y abrir otro?", "Descartar y abrir", "Cancelar"):
            return
        try:
            doc = ec.open_working(path)
        except Exception as e:
            inform(self, "No se pudo abrir", str(e), error=True)
            return
        self._clear()
        self.doc = doc
        self.path = path
        self.start_view.hide()
        self.editor_view.show()
        y = 0.0
        maxw = max(p.rect.width for p in doc)
        for i, page in enumerate(doc):
            w, h = page.rect.width, page.rect.height
            f = PageFrame(i, w, h)
            f.setPos((maxw - w) / 2, y)
            self.scene.addItem(f)
            self.frames.append(f)
            y += h + GAP
        self.scene.setSceneRect(QRectF(-GAP, -GAP, maxw + 2 * GAP, y + GAP))
        self.page_total.setText(f"de {len(doc)}")
        self.title.setText(os.path.basename(path))
        self.title.setToolTip(path)
        self._build_fields()
        notes = []
        if is_signed(path) and settings().get("confirm_signed"):
            notes.append("Este PDF tiene firma digital: en la copia editada la firma aparecerá como no válida.")
        if self.fields:
            notes.append("Este PDF tiene campos para llenar: haz clic en los recuadros celestes y escribe.")
        if notes:
            self.banner.show_text(" ".join(notes))
        else:
            self.banner.hide()
        self.result.hide()
        self.error.hide()
        self.dirty = False
        self.set_tool("select")
        QTimer.singleShot(0, self._initial_view)

    def _initial_view(self):
        self.fit_width()
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().minimum())
        self._update_page_label()
        self.render_visible()

    def _clear(self):
        self.scene.clear()
        self.frames = []
        self.undo_stack = []
        self.seg_cache = {}
        self.word_cache = {}
        self.fields = []
        self._hover = None
        self._temp = None
        if self.doc:
            try:
                self.doc.close()
            except Exception:
                pass
        self.doc = None
        self._update_undo()

    def close_doc(self):
        if self.dirty and not ask(self, "Cambios sin guardar", "Hay cambios sin guardar. ¿Quieres descartarlos?",
                                  "Descartar", "Cancelar"):
            return
        self._clear()
        self.dirty = False
        self.editor_view.hide()
        self.start_view.show()

    def has_unsaved(self):
        return bool(self.doc) and self.dirty

    # ------------------------------------------------------------------
    # Formularios
    # ------------------------------------------------------------------
    def _build_fields(self):
        for i, page in enumerate(self.doc):
            try:
                widgets = list(page.widgets() or [])
            except Exception:
                widgets = []
            for w in widgets:
                r = w.rect
                t = w.field_type
                qw = None
                if t in (pymupdf.PDF_WIDGET_TYPE_TEXT,):
                    qw = QLineEdit(w.field_value or "")
                    qw.textEdited.connect(self._mark_dirty)
                elif t in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                    qw = QCheckBox()
                    val = w.field_value
                    qw.setChecked(bool(val) and str(val) not in ("Off", "False", "0"))
                    qw.toggled.connect(self._mark_dirty)
                elif t in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
                    qw = QComboBox()
                    qw.setEditable(True)
                    for v in w.choice_values or []:
                        qw.addItem(v[1] if isinstance(v, (list, tuple)) else str(v))
                    qw.setCurrentText(w.field_value or "")
                    qw.currentTextChanged.connect(self._mark_dirty)
                if qw is None:
                    continue
                fs = max(6, int(min(r.height * 0.62, (w.text_fontsize or 0) or 99)))
                if isinstance(qw, QCheckBox):
                    ind = max(6, int(min(r.width, r.height)) - 4)
                    qw.setStyleSheet(
                        f"QCheckBox {{ background: rgba(214,228,255,200); border: 1px solid #8FB0F0; padding: 1px;"
                        f" spacing: 0; min-height: 0; }}"
                        f"QCheckBox::indicator {{ width: {ind}px; height: {ind}px; border: 1px solid #5C7FC8;"
                        f" border-radius: 1px; background: white; }}"
                        f"QCheckBox::indicator:checked {{ background: #2155D6; image: none; }}")
                else:
                    qw.setStyleSheet(f"* {{ background: rgba(214,228,255,200); border: 1px solid #8FB0F0;"
                                     f" border-radius: 2px; padding: 0 2px; font-size: {fs}px; color: black;"
                                     f" min-height: 0; }}")
                proxy = self.scene.addWidget(qw)
                proxy.setParentItem(self.frames[i])
                proxy.setPos(r.x0, r.y0)
                proxy.resize(r.width, r.height)
                proxy.setZValue(6)
                self.fields.append((i, w.xref, t, qw))

    def _field_values(self):
        out = []
        for page, xref, t, qw in self.fields:
            if isinstance(qw, QLineEdit):
                v = qw.text()
            elif isinstance(qw, QCheckBox):
                v = qw.isChecked()
            else:
                v = qw.currentText()
            out.append({"page": page, "xref": xref, "value": v})
        return out

    def _mark_dirty(self, *a):
        self.dirty = True

    # ------------------------------------------------------------------
    # Dibujo de páginas
    # ------------------------------------------------------------------
    def _schedule_render(self, *a):
        self.render_timer.start()
        self._update_page_label()

    def render_visible(self):
        if not self.doc:
            return
        vis = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        dpr = self.view.devicePixelRatioF() or 1.0
        target = min(4.5, self.zoom * dpr)
        visible = [f for f in self.frames if f.sceneBoundingRect().intersects(vis)]
        if not visible:
            return
        lo = max(0, visible[0].index - 1)
        hi = min(len(self.frames) - 1, visible[-1].index + 1)
        for f in self.frames:
            if lo <= f.index <= hi:
                if abs(f.rendered - target) / target > 0.02:
                    self._render_frame(f, target)
            elif f.pix is not None and abs(f.index - visible[0].index) > 6:
                self.scene.removeItem(f.pix)
                f.pix = None
                f.rendered = 0.0

    def _render_frame(self, f, scale):
        page = self.doc[f.index]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=True)
        qp = QPixmap()
        qp.loadFromData(pix.tobytes("ppm"))
        if f.pix is None:
            from PySide6.QtWidgets import QGraphicsPixmapItem
            f.pix = QGraphicsPixmapItem(f)
            f.pix.setTransformationMode(Qt.SmoothTransformation)
            f.pix.setZValue(0)
            f.pix.setAcceptedMouseButtons(Qt.NoButton)
        f.pix.setPixmap(qp)
        f.pix.setScale(1.0 / scale)
        f.rendered = scale

    def rerender_page(self, index):
        f = self.frames[index]
        f.rendered = 0.0
        self.seg_cache.pop(index, None)
        self.word_cache.pop(index, None)
        dpr = self.view.devicePixelRatioF() or 1.0
        self._render_frame(f, min(4.5, self.zoom * dpr))

    # ------------------------------------------------------------------
    # Zoom y páginas
    # ------------------------------------------------------------------
    def set_zoom(self, z):
        z = max(0.25, min(5.0, z))
        self.zoom = z
        self.view.resetTransform()
        self.view.scale(z, z)
        self.zoom_label.setText(f"{round(z / PX_PER_PT_100 * 100)} %")
        self._schedule_render()

    def zoom_by(self, k):
        self.set_zoom(self.zoom * k)

    def fit_width(self):
        if not self.frames:
            return
        maxw = max(f.rect().width() for f in self.frames)
        avail = self.view.viewport().width() - 30
        self.set_zoom(max(0.25, avail / (maxw + 2 * GAP)))

    def frame_at(self, sp: QPointF):
        for f in self.frames:
            if f.sceneBoundingRect().contains(sp):
                return f
        return None

    def current_page(self):
        if not self.frames:
            return 0
        c = self.view.mapToScene(self.view.viewport().rect().center())
        for f in self.frames:
            r = f.sceneBoundingRect()
            if r.top() - GAP <= c.y() <= r.bottom() + GAP / 2:
                return f.index
        return 0

    def _update_page_label(self):
        if self.frames and not self.page_edit.hasFocus():
            self.page_edit.setText(str(self.current_page() + 1))

    def goto_page(self, i):
        if not self.frames:
            return
        i = max(0, min(len(self.frames) - 1, i))
        r = self.frames[i].sceneBoundingRect()
        self.view.verticalScrollBar().setValue(int(self.view.mapFromScene(QPointF(0, r.top() - GAP / 2)).y()
                                                   + self.view.verticalScrollBar().value()))
        self._update_page_label()

    def visible_frame(self):
        return self.frames[self.current_page()] if self.frames else None

    # ------------------------------------------------------------------
    # Herramientas
    # ------------------------------------------------------------------
    def set_tool(self, key):
        if key in ("sign", "stamp"):
            self.tool_buttons[self.tool].setChecked(True)
            if self.doc:
                self.place_signature() if key == "sign" else self.place_stamp()
            return
        self.tool = key
        self.tool_buttons[key].setChecked(True)
        self.hint.setText(TOOL_HINT[key])
        self._clear_hover()
        if key == "select":
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            self.view.viewport().setCursor(Qt.ArrowCursor)
        else:
            self.view.setDragMode(QGraphicsView.NoDrag)
            cur = {"text": Qt.IBeamCursor, "fix": Qt.PointingHandCursor, "note": Qt.PointingHandCursor}.get(key, Qt.CrossCursor)
            self.view.viewport().setCursor(cur)
            self.scene.clearSelection()
        if key in self.tool_colors:
            self.color_group.button(self.tool_colors[key]).setChecked(True)
        self._update_props_visibility()

    def _update_props_visibility(self, item=None):
        tool = self.tool
        kind = getattr(item, "kind", None)
        show_font = tool == "text" or kind == "text"
        show_width = tool in ("pen", "rect") or kind in ("ink", "rect")
        show_color = tool in ("text", "pen", "rect", "highlight", "underline", "strike") or kind in (
            "text", "ink", "rect", "highlight", "underline", "strike")
        self.font_row.setVisible(show_font)
        self.width_row.setVisible(show_width)
        self.color_row.setVisible(show_color)
        self.props.setVisible(show_font or show_width or show_color)

    def current_color(self):
        b = self.color_group.checkedButton()
        return QColor(b.property("hex")) if b else QColor("black")

    def _selection_changed(self):
        sel = [i for i in self.scene.selectedItems() if isinstance(i, Overlay)]
        if self.tool == "select":
            self._update_props_visibility(sel[0] if sel else None)
        if len(sel) == 1:
            it = sel[0]
            widgets = (self.prop_font, self.prop_size, self.prop_bold, self.prop_width)
            for w in widgets:
                w.blockSignals(True)
            if isinstance(it, TextBox):
                self.prop_font.setCurrentText(it.family)
                self.prop_size.setValue(it.size_)
                self.prop_bold.setChecked(it.bold)
            if hasattr(it, "width") and isinstance(it, (InkItem, RectBox)):
                for i in range(self.prop_width.count()):
                    if abs(self.prop_width.itemData(i) - it.width) < 0.01:
                        self.prop_width.setCurrentIndex(i)
            col = getattr(it, "color", None)
            if isinstance(col, QColor):
                for b in self.color_group.buttons():
                    b.blockSignals(True)
                    b.setChecked(QColor(b.property("hex")).rgb() == col.rgb())
                    b.blockSignals(False)
            for w in widgets:
                w.blockSignals(False)

    def _props_changed(self, *a):
        st = settings()
        st.data["editor_font"] = self.prop_font.currentText()
        st.data["editor_size"] = self.prop_size.value()
        if self.tool in self.tool_colors:
            self.tool_colors[self.tool] = self.color_group.checkedId()
        for it in self.scene.selectedItems():
            if isinstance(it, TextBox):
                it.set_style(self.prop_font.currentText(), self.prop_size.value(), self.current_color(),
                             self.prop_bold.isChecked())
                self.dirty = True
            elif isinstance(it, InkItem):
                it.set_style(self.current_color(), self.prop_width.currentData())
                self.dirty = True
            elif isinstance(it, RectBox):
                it.color, it.width = self.current_color(), self.prop_width.currentData()
                it.update()
                self.dirty = True
            elif isinstance(it, MarkupItem):
                it.color = self.current_color()
                it.update()
                self.dirty = True
        focus = self.scene.focusItem()
        if isinstance(focus, TextBox) and focus.editing() and not focus.isSelected():
            focus.set_style(self.prop_font.currentText(), self.prop_size.value(), self.current_color(),
                            self.prop_bold.isChecked())

    # ------------------------------------------------------------------
    # Agregar / quitar elementos
    # ------------------------------------------------------------------
    def add_item(self, item, frame, pos=None, record=True):
        item.editor = self
        item.setParentItem(frame)
        if pos is not None:
            item.setPos(pos)
        if record:
            self.push_undo(("add", item))
        self.dirty = True
        return item

    def remove_item(self, item, record=True):
        parent = item.parentItem()
        if parent is None:
            return
        if record:
            self.push_undo(("del", item, parent, QPointF(item.pos())))
        item.setSelected(False)
        self.scene.removeItem(item)
        self.dirty = True

    def delete_selected(self):
        items = [i for i in self.scene.selectedItems() if isinstance(i, Overlay)]
        if not items:
            return
        for it in items:
            self.remove_item(it)

    def push_undo(self, action):
        self.undo_stack.append(action)
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.dirty = True
        self._update_undo()

    def _update_undo(self):
        self.b_undo.setEnabled(bool(self.undo_stack))

    def _shortcut_undo(self):
        focus = self.scene.focusItem()
        if isinstance(focus, TextBox) and focus.editing():
            focus.document().undo()
            return
        self.undo()

    def undo(self):
        if not self.undo_stack:
            return
        a = self.undo_stack.pop()
        kind = a[0]
        if kind == "add":
            it = a[1]
            if it.scene():
                it.setSelected(False)
                self.scene.removeItem(it)
        elif kind == "del":
            it, parent, pos = a[1], a[2], a[3]
            it.setParentItem(parent)
            it.setPos(pos)
        elif kind == "move":
            for it, old in a[1]:
                it.setPos(old)
        elif kind == "resize":
            a[1].set_rect(a[2])
        elif kind == "fix":
            page_no, data = a[1], a[2]
            ec.restore_page(self.doc, page_no, data)
            self.rerender_page(page_no)
        self._update_undo()

    # ------------------------------------------------------------------
    # Eventos de las herramientas
    # ------------------------------------------------------------------
    def tool_press(self, frame, p):
        t = self.tool
        self.error.hide()
        if t == "text":
            box = TextBox(self.prop_font.currentText(), self.prop_size.value(), self.current_color(),
                          self.prop_bold.isChecked())
            self.add_item(box, frame, QPointF(p.x(), p.y() - self.prop_size.value() * 0.6))
            self.set_tool("select")
            self.scene.clearSelection()
            box.start_edit()
            self.hint.setText("Escribe el texto. Para terminar, haz clic fuera del cuadro. "
                              "Puedes arrastrarlo para moverlo.")
        elif t == "fix":
            self._do_fix(frame, p)
        elif t in ("highlight", "underline", "strike"):
            words = self._words(frame.index)
            if words:
                i = self._nearest_word(words, p)
                self._drag = {"frame": frame, "mode": "words", "start": i}
                rects = self._word_rects(words, i, i) if i is not None else []
            else:
                self._drag = {"frame": frame, "mode": "rect", "start": QPointF(p)}
                rects = []
            self._temp = MarkupItem(t, rects, self.current_color())
            self._temp.setParentItem(frame)
        elif t == "note":
            dlg = NoteDialog(parent=self)
            if dlg.exec() and dlg.text():
                n = NoteItem(dlg.text())
                self.add_item(n, frame, QPointF(p.x() - 4, p.y() - 4))
        elif t in ("whiteout", "rect"):
            self._drag = {"frame": frame, "start": QPointF(p)}
            if t == "whiteout":
                self._temp = WhiteoutBox(1, 1)
            else:
                self._temp = RectBox(1, 1, self.current_color(), self.prop_width.currentData())
            self._temp.editor = self
            self._temp.setParentItem(frame)
            self._temp.setPos(p)
        elif t == "pen":
            ink = InkItem(self.current_color(), self.prop_width.currentData())
            ink.editor = self
            ink.setParentItem(frame)
            ink.add_point(p)
            self._drag = {"frame": frame}
            self._temp = ink

    def tool_move(self, frame, p, pressed):
        t = self.tool
        if not pressed:
            if t == "fix":
                self._hover_fix(frame, p)
            return
        if not self._drag or self._temp is None:
            return
        f = self._drag["frame"]
        if frame is not f:
            # convertir al sistema de la página donde empezó
            if p is None:
                return
            p = f.mapFromItem(frame, p) if frame is not None else p
        if t in ("highlight", "underline", "strike"):
            if self._drag["mode"] == "words":
                words = self._words(f.index)
                j = self._nearest_word(words, p)
                i = self._drag["start"]
                if i is None:
                    self._drag["start"] = i = j
                if i is not None and j is not None:
                    self._temp.set_rects(self._word_rects(words, min(i, j), max(i, j)))
            else:
                r = QRectF(self._drag["start"], p).normalized()
                self._temp.set_rects([r])
        elif t in ("whiteout", "rect"):
            r = QRectF(self._drag["start"], p).normalized()
            self._temp.setPos(r.topLeft())
            self._temp.set_rect(QRectF(0, 0, max(1, r.width()), max(1, r.height())))
        elif t == "pen":
            self._temp.add_point(p)

    def tool_release(self, frame, p):
        t = self.tool
        temp, self._temp = self._temp, None
        drag, self._drag = self._drag, None
        if temp is None or drag is None:
            return
        f = drag["frame"]
        if t in ("highlight", "underline", "strike"):
            if not temp.rects or all(r.width() < 2 for r in temp.rects):
                self.scene.removeItem(temp)
                return
            self.add_item(temp, f)
        elif t in ("whiteout", "rect"):
            if temp.r.width() < 3 or temp.r.height() < 3:
                self.scene.removeItem(temp)
                return
            self.add_item(temp, f)
        elif t == "pen":
            self.add_item(temp, f)

    # --- palabras del documento (para resaltar) ---
    def _words(self, index):
        if index not in self.word_cache:
            try:
                ws = self.doc[index].get_text("words", sort=True)
            except Exception:
                ws = []
            self.word_cache[index] = ws
        return self.word_cache[index]

    @staticmethod
    def _nearest_word(words, p):
        best, bd = None, 1e9
        for i, w in enumerate(words):
            x0, y0, x1, y1 = w[:4]
            dx = 0 if x0 <= p.x() <= x1 else min(abs(p.x() - x0), abs(p.x() - x1))
            dy = 0 if y0 <= p.y() <= y1 else min(abs(p.y() - y0), abs(p.y() - y1))
            d = dx + dy * 3
            if d < bd:
                best, bd = i, d
        return best if bd < 40 else None

    @staticmethod
    def _word_rects(words, i, j):
        rects = []
        cur, key = None, None
        for w in words[i:j + 1]:
            k = (w[5], w[6])
            r = QRectF(QPointF(w[0], w[1]), QPointF(w[2], w[3]))
            if cur is not None and k == key and abs(r.center().y() - cur.center().y()) < r.height() * 0.6:
                cur = cur.united(r)
            else:
                if cur is not None:
                    rects.append(cur)
                cur, key = r, k
        if cur is not None:
            rects.append(cur)
        return rects

    # --- corregir texto ---
    def _segments(self, index):
        if index not in self.seg_cache:
            try:
                self.seg_cache[index] = ec.text_segments(self.doc[index])
            except Exception:
                self.seg_cache[index] = []
        return self.seg_cache[index]

    def _seg_at(self, frame, p):
        if frame is None or p is None:
            return None
        for s in self._segments(frame.index):
            x0, y0, x1, y1 = s["rect"]
            if x0 - 1 <= p.x() <= x1 + 1 and y0 <= p.y() <= y1:
                return s
        return None

    def _clear_hover(self):
        if self._hover is not None and self._hover.scene():
            self.scene.removeItem(self._hover)
        self._hover = None
        self._hover_seg = None

    def _hover_fix(self, frame, p):
        seg = self._seg_at(frame, p)
        if seg is self._hover_seg and self._hover is not None:
            return
        self._clear_hover()
        if seg:
            x0, y0, x1, y1 = seg["rect"]
            h = QGraphicsRectItem(QRectF(x0 - 1.5, y0 - 1, x1 - x0 + 3, y1 - y0 + 2), frame)
            c = QColor(theme.colors()["accent"])
            h.setPen(QPen(c, 0))
            c.setAlpha(40)
            h.setBrush(c)
            h.setZValue(20)
            h.setAcceptedMouseButtons(Qt.NoButton)
            self._hover = h
            self._hover_seg = seg

    def _do_fix(self, frame, p):
        seg = self._seg_at(frame, p)
        if seg is None:
            if not ec.has_text(self.doc[frame.index]):
                self.error.show_error("Esta página es escaneada (es una foto del papel): no tiene texto para "
                                      "corregir. Usa «Tapar» para cubrir lo que quieres cambiar y luego "
                                      "«Escribir texto» encima.")
            return
        dlg = FixTextDialog(seg, self)
        if not dlg.exec():
            return
        text, family, size, bold = dlg.values()
        if text == seg["text"] and size == seg["size"]:
            return
        snap = ec.page_snapshot(self.doc, frame.index)
        try:
            ec.replace_segment(self.doc, frame.index, seg, text, family=family, size=size, bold=bold)
        except Exception as e:
            ec.restore_page(self.doc, frame.index, snap)
            self.error.show_error(f"No se pudo corregir ese texto: {e}")
            return
        self.push_undo(("fix", frame.index, snap))
        self._clear_hover()
        self.rerender_page(frame.index)

    # --- firma y sello ---
    def _place_box(self, item, w, h, corner="center"):
        f = self.visible_frame()
        if f is None:
            return
        vis = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        vis_local = f.mapFromScene(vis).boundingRect().intersected(f.rect())
        if corner == "topright":
            x = vis_local.right() - w - 30
            y = max(vis_local.top() + 30, 20)
        else:
            x = vis_local.center().x() - w / 2
            y = vis_local.center().y() - h / 2
        self.add_item(item, f, QPointF(max(5, x), max(5, y)))
        self.set_tool("select")
        self.scene.clearSelection()
        item.setSelected(True)
        self.hint.setText("Arrastra para moverlo a su lugar. Para agrandar o achicar, arrastra el cuadrito azul "
                          "de la esquina.")

    def place_signature(self):
        dlg = SignatureDialog(self)
        if not dlg.exec() or not dlg.chosen:
            return
        with open(dlg.chosen, "rb") as fh:
            png = fh.read()
        pm = QPixmap()
        pm.loadFromData(png)
        if pm.isNull():
            inform(self, "Imagen no válida", "No se pudo leer esa imagen.", error=True)
            return
        w = 150.0
        h = w * pm.height() / max(1, pm.width())
        if h > 110:
            h = 110.0
            w = h * pm.width() / max(1, pm.height())
        self._place_box(ImageBox(png, w, h), w, h)

    def place_stamp(self):
        dlg = StampDialog(self)
        if not dlg.exec():
            return
        title, lines, color = dlg.data()
        w, h = stamp_size(lines)
        self._place_box(StampBox(title, lines, QColor(color), w, h), w, h, corner="topright")

    def edit_note(self, note):
        dlg = NoteDialog(note.text, self)
        if dlg.exec() and dlg.text():
            note.set_text(dlg.text())
            self.dirty = True

    # ------------------------------------------------------------------
    # Guardar
    # ------------------------------------------------------------------
    def collect_specs(self):
        specs = []
        for f in self.frames:
            for it in f.childItems():
                if isinstance(it, Overlay):
                    s = it.spec()
                    if s:
                        specs.append(s)
        return specs

    def save(self):
        if not self.doc:
            return
        focus = self.scene.focusItem()
        if focus is not None:
            focus.clearFocus()
        self.error.hide()
        out = choose_output(self, self.path, "editado", ".pdf", "PDF (*.pdf)")
        if not out:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ec.save_copy(self.doc, self.collect_specs(), self._field_values(), out)
        except PermissionError:
            QApplication.restoreOverrideCursor()
            self.error.show_error("No se pudo guardar. Puede que el archivo esté abierto en otro programa.")
            return
        except Exception as e:
            QApplication.restoreOverrideCursor()
            self.error.show_error(f"No se pudo guardar: {e}")
            return
        QApplication.restoreOverrideCursor()
        self.dirty = False
        self.result.show_result(out, f"Se guardó una copia con tus cambios: {os.path.basename(out)}\n"
                                     "Puedes seguir editando; para guardar de nuevo pulsa «Guardar PDF».")
        if settings().get("open_when_done"):
            open_path(out)
