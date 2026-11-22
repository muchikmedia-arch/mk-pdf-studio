"""Elementos que se agregan sobre las páginas en el editor (texto, firma, sello, dibujo…)."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen, QPixmap,
                           QTextCursor)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsTextItem

from ..core.editor_core import stamp_layout


def rgbf(c: QColor):
    return (c.redF(), c.greenF(), c.blueF())


class PageFrame(QGraphicsRectItem):
    """Una página del documento: fondo blanco + imagen renderizada; los elementos agregados son sus hijos."""

    def __init__(self, index, w, h):
        super().__init__(0, 0, w, h)
        self.index = index
        self.setBrush(QBrush(QColor("white")))
        self.setPen(QPen(QColor("#B8C0CC"), 0))
        self.pix = None
        self.rendered = 0.0
        self.setZValue(0)


class Overlay:
    kind = ""
    editor = None

    def page_index(self):
        p = self.parentItem()
        return p.index if p is not None else 0

    def spec(self):
        return None


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------

class TextBox(QGraphicsTextItem, Overlay):
    kind = "text"

    def __init__(self, family="Arial", size=12, color=QColor("black"), bold=False):
        super().__init__()
        self.family, self.size_, self.bold, self.color = family, int(size), bold, QColor(color)
        self.document().setDocumentMargin(0)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsFocusable)
        self.apply_style()
        self.setZValue(10)

    def apply_style(self):
        f = QFont(self.family)
        f.setPixelSize(max(4, int(self.size_)))
        f.setBold(self.bold)
        f.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(f)
        self.setDefaultTextColor(self.color)

    def set_style(self, family=None, size=None, color=None, bold=None):
        if family:
            self.family = family
        if size:
            self.size_ = int(size)
        if color is not None:
            self.color = QColor(color)
        if bold is not None:
            self.bold = bold
        self.apply_style()
        self.update()

    def start_edit(self):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        c = self.textCursor()
        c.movePosition(QTextCursor.End)
        self.setTextCursor(c)

    def editing(self):
        return bool(self.textInteractionFlags() & Qt.TextEditorInteraction)

    def mouseDoubleClickEvent(self, e):
        if not self.editing():
            self.start_edit()
        super().mouseDoubleClickEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        c = self.textCursor()
        c.clearSelection()
        self.setTextCursor(c)
        if not self.toPlainText().strip() and self.editor:
            self.editor.remove_item(self, record=False)

    def paint(self, painter, option, widget=None):
        from PySide6.QtWidgets import QStyle
        option.state &= ~QStyle.State_Selected
        option.state &= ~QStyle.State_HasFocus
        super().paint(painter, option, widget)
        if self.isSelected() or self.editing():
            pen = QPen(QColor("#2155D6"), 0, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect().adjusted(-2, -2, 2, 2))

    def spec(self):
        lines = []
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            layout = block.layout()
            bpos = layout.position()
            text = block.text()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                seg = text[line.textStart(): line.textStart() + line.textLength()].rstrip()
                x = self.pos().x() + bpos.x() + line.x()
                y = self.pos().y() + bpos.y() + line.y() + line.ascent()
                lines.append((x, y, seg))
            block = block.next()
        if not any(t for _, _, t in lines):
            return None
        return {"type": "text", "page": self.page_index(), "lines": lines, "size": float(self.size_),
                "font": self.family, "bold": self.bold, "italic": False, "color": rgbf(self.color)}


# ---------------------------------------------------------------------------
# Elementos con tamaño ajustable
# ---------------------------------------------------------------------------

class ResizableItem(QGraphicsItem, Overlay):
    keep_aspect = False
    min_size = 8.0

    def __init__(self, w, h):
        super().__init__()
        self.r = QRectF(0, 0, w, h)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self._resizing = False
        self._start_rect = None
        self.setZValue(8)

    def handle_size(self):
        views = self.scene().views() if self.scene() else []
        scale = views[0].transform().m11() if views else 1.0
        return 11.0 / max(0.1, scale)

    def handle_rect(self):
        hs = self.handle_size()
        return QRectF(self.r.right() - hs / 2, self.r.bottom() - hs / 2, hs, hs)

    def boundingRect(self):
        hs = self.handle_size()
        return self.r.adjusted(-2, -2, hs, hs)

    def paint_selection(self, painter):
        if self.isSelected():
            painter.setPen(QPen(QColor("#2155D6"), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.r)
            painter.setPen(QPen(QColor("white"), 0))
            painter.setBrush(QColor("#2155D6"))
            painter.drawRect(self.handle_rect())

    def hoverMoveEvent(self, e):
        if self.isSelected() and self.handle_rect().contains(e.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(e)

    def mousePressEvent(self, e):
        if self.isSelected() and self.handle_rect().contains(e.pos()):
            self._resizing = True
            self._start_rect = QRectF(self.r)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing:
            self.prepareGeometryChange()
            w = max(self.min_size, e.pos().x() - self.r.left())
            h = max(self.min_size, e.pos().y() - self.r.top())
            if self.keep_aspect and self._start_rect.width() > 0:
                ratio = self._start_rect.height() / self._start_rect.width()
                h = w * ratio
            self.r = QRectF(self.r.left(), self.r.top(), w, h)
            self.update()
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._resizing:
            self._resizing = False
            if self.editor and self._start_rect != self.r:
                self.editor.push_undo(("resize", self, self._start_rect))
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def set_rect(self, r):
        self.prepareGeometryChange()
        self.r = QRectF(r)
        self.update()

    def page_rect(self):
        p = self.pos()
        return (p.x() + self.r.left(), p.y() + self.r.top(), p.x() + self.r.right(), p.y() + self.r.bottom())


class ImageBox(ResizableItem):
    kind = "image"
    keep_aspect = True

    def __init__(self, png_bytes: bytes, w, h):
        super().__init__(w, h)
        self.png = png_bytes
        self.img = QImage.fromData(png_bytes)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.r, self.img)
        self.paint_selection(painter)

    def spec(self):
        return {"type": "image", "page": self.page_index(), "rect": self.page_rect(), "png": self.png}


class StampBox(ResizableItem):
    kind = "stamp"
    keep_aspect = True

    def __init__(self, title, lines, color: QColor, w, h):
        super().__init__(w, h)
        self.title, self.lines, self.color = title, list(lines), QColor(color)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.r
        pen = QPen(self.color, max(1.0, r.height() * 0.018))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        rad = min(r.width(), r.height()) * 0.06
        painter.drawRoundedRect(r, rad, rad)
        m = r.height() * 0.035
        painter.setPen(QPen(self.color, max(0.5, r.height() * 0.007)))
        painter.drawRoundedRect(r.adjusted(m, m, -m, -m), rad, rad)
        painter.setPen(self.color)
        for row in stamp_layout((r.left(), r.top(), r.right(), r.bottom()), self.title, self.lines):
            f = QFont("Arial")
            f.setPixelSize(100)
            f.setBold(row["bold"])
            fm = QFontMetricsF(f)
            w100 = fm.horizontalAdvance(row["text"]) or 1
            size = row["size"]
            if w100 * size / 100 > r.width() * 0.9:
                size = r.width() * 0.9 * 100 / w100
            k = size / 100.0
            painter.save()
            painter.translate(row["cx"] - w100 * k / 2, row["baseline"])
            painter.scale(k, k)
            painter.setFont(f)
            painter.drawText(QPointF(0, 0), row["text"])
            painter.restore()
        self.paint_selection(painter)

    def spec(self):
        return {"type": "stamp", "page": self.page_index(), "rect": self.page_rect(), "title": self.title,
                "lines": self.lines, "color": rgbf(self.color)}


class RectBox(ResizableItem):
    kind = "rect"

    def __init__(self, w, h, color=QColor("red"), width=1.5):
        super().__init__(w, h)
        self.color, self.width = QColor(color), width
        self.min_size = 3

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(self.color, self.width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.r)
        self.paint_selection(painter)

    def spec(self):
        return {"type": "rect", "page": self.page_index(), "rect": self.page_rect(), "color": rgbf(self.color),
                "width": self.width}


class WhiteoutBox(ResizableItem):
    kind = "redact"

    def __init__(self, w, h):
        super().__init__(w, h)
        self.min_size = 3
        self.setZValue(5)

    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(QColor("#9AA3B2"), 0, Qt.DashLine))
        painter.setBrush(QColor("white"))
        painter.drawRect(self.r)
        self.paint_selection(painter)

    def spec(self):
        return {"type": "redact", "page": self.page_index(), "rect": self.page_rect()}


# ---------------------------------------------------------------------------
# Dibujo, marcas y notas
# ---------------------------------------------------------------------------

class InkItem(QGraphicsPathItem, Overlay):
    kind = "ink"

    def __init__(self, color=QColor("#C62828"), width=2.0):
        super().__init__()
        self.color, self.width = QColor(color), width
        self.strokes = [[]]
        pen = QPen(self.color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setZValue(9)

    def add_point(self, p: QPointF):
        self.strokes[-1].append((p.x(), p.y()))
        path = QPainterPath()
        for stroke in self.strokes:
            if not stroke:
                continue
            path.moveTo(*stroke[0])
            if len(stroke) == 1:
                path.lineTo(stroke[0][0] + 0.01, stroke[0][1])
            for x, y in stroke[1:]:
                path.lineTo(x, y)
        self.setPath(path)

    def set_style(self, color=None, width=None):
        if color is not None:
            self.color = QColor(color)
        if width:
            self.width = width
        self.setPen(QPen(self.color, self.width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

    def paint(self, painter, option, widget=None):
        from PySide6.QtWidgets import QStyle
        option.state &= ~QStyle.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("#2155D6"), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def spec(self):
        dx, dy = self.pos().x(), self.pos().y()
        strokes = [[(x + dx, y + dy) for x, y in s] for s in self.strokes if s]
        if not strokes:
            return None
        return {"type": "ink", "page": self.page_index(), "strokes": strokes, "color": rgbf(self.color),
                "width": self.width}


MARKUP_COLORS = {"highlight": QColor(255, 226, 0), "underline": QColor(0, 90, 220), "strike": QColor(210, 30, 30)}


class MarkupItem(QGraphicsItem, Overlay):
    """Resaltado, subrayado o tachado sobre el texto."""

    def __init__(self, kind, rects, color=None):
        super().__init__()
        self.kind = kind
        self.rects = [QRectF(r) for r in rects]
        self.color = QColor(color) if color is not None else MARKUP_COLORS[kind]
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setZValue(7)

    def set_rects(self, rects):
        self.prepareGeometryChange()
        self.rects = [QRectF(r) for r in rects]
        self.update()

    def boundingRect(self):
        if not self.rects:
            return QRectF()
        r = QRectF(self.rects[0])
        for x in self.rects[1:]:
            r = r.united(x)
        return r.adjusted(-2, -2, 2, 2)

    def shape(self):
        path = QPainterPath()
        for r in self.rects:
            path.addRect(r)
        return path

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if self.kind == "highlight":
            c = QColor(self.color)
            c.setAlpha(110)
            painter.setPen(Qt.NoPen)
            painter.setBrush(c)
            painter.setCompositionMode(QPainter.CompositionMode_Multiply)
            for r in self.rects:
                painter.drawRect(r)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        else:
            for r in self.rects:
                w = max(0.8, r.height() * 0.07)
                painter.setPen(QPen(self.color, w))
                y = r.bottom() - w if self.kind == "underline" else r.center().y()
                painter.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        if self.isSelected():
            painter.setPen(QPen(QColor("#2155D6"), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            for r in self.rects:
                painter.drawRect(r)

    def spec(self):
        if not self.rects:
            return None
        return {"type": self.kind, "page": self.page_index(), "color": rgbf(self.color),
                "rects": [(r.left(), r.top(), r.right(), r.bottom()) for r in self.rects]}


class NoteItem(QGraphicsItem, Overlay):
    kind = "note"
    SIZE = 20.0

    def __init__(self, text):
        super().__init__()
        self.text = text
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable)
        self.setToolTip(text)
        self.setZValue(11)
        self.setCursor(Qt.PointingHandCursor)

    def boundingRect(self):
        return QRectF(-1, -1, self.SIZE + 2, self.SIZE + 2)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        s = self.SIZE
        painter.setPen(QPen(QColor("#8A5A00"), 1))
        painter.setBrush(QColor("#FFD54F"))
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(s, 0)
        path.lineTo(s, s * 0.72)
        path.lineTo(s * 0.45, s * 0.72)
        path.lineTo(s * 0.22, s)
        path.lineTo(s * 0.25, s * 0.72)
        path.lineTo(0, s * 0.72)
        path.closeSubpath()
        painter.drawPath(path)
        painter.setPen(QPen(QColor("#8A5A00"), 1.2))
        painter.drawLine(QPointF(s * 0.2, s * 0.25), QPointF(s * 0.8, s * 0.25))
        painter.drawLine(QPointF(s * 0.2, s * 0.47), QPointF(s * 0.65, s * 0.47))
        if self.isSelected():
            painter.setPen(QPen(QColor("#2155D6"), 0, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.boundingRect())

    def mouseDoubleClickEvent(self, e):
        if self.editor:
            self.editor.edit_note(self)

    def set_text(self, text):
        self.text = text
        self.setToolTip(text)

    def spec(self):
        return {"type": "note", "page": self.page_index(), "point": (self.pos().x(), self.pos().y()),
                "text": self.text}
