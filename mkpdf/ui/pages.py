"""Páginas de cada herramienta (Convertir y Herramientas de oficina)."""
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from . import theme
from .toolpage import ToolPage
from .widgets import IconLabel, choose_output, icon_button, inform, open_path, output_folder, show_in_folder
from ..core.common import output_path, unique_path, human_size


def _row(*widgets, stretch=True):
    row = QHBoxLayout()
    for w in widgets:
        if isinstance(w, str):
            lab = QLabel(w)
            row.addWidget(lab)
        else:
            row.addWidget(w)
    if stretch:
        row.addStretch(1)
    return row


def _hint(text):
    l = QLabel(text)
    l.setObjectName("Muted")
    l.setWordWrap(True)
    return l


# =============================================================================
# CONVERTIR
# =============================================================================

class WordPage(ToolPage):
    title = "PDF a Word"
    subtitle = ("Convierte el PDF en un documento de Word que puedes editar. Se respetan los márgenes, "
                "las sangrías, las tablas y las imágenes. Los PDF escaneados se reconocen con OCR.")
    icon_name = "word"
    action_text = "Convertir a Word"
    working_text = "Convirtiendo a Word…"
    modifies = False

    def build_options(self, lay):
        self.pages_option(lay)
        self.force = QCheckBox("Reconocer el texto con OCR aunque el PDF parezca digital "
                               "(útil cuando el texto sale con símbolos raros)")
        lay.addWidget(self.force)
        return True

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "", ".docx", "Documento de Word (*.docx)")
        if not out:
            return None
        return ("mkpdf.core.word:pdf_to_word", (src, out),
                {"pages": self.selected_pages(), "force_ocr": self.force.isChecked()}, out)

    def describe(self, r):
        txt = f"Se convirtieron {r['pages']} página{'s' if r['pages'] != 1 else ''}."
        if r.get("scanned"):
            txt += (f" {r['scanned']} {'eran' if r['scanned'] != 1 else 'era'} escaneada{'s' if r['scanned'] != 1 else ''} "
                    "y se reconocieron con OCR: revisa el texto, puede haber alguna letra mal leída "
                    "donde el escaneo no se ve claro.")
        return txt + f"\n\nSe guardó como: {os.path.basename(self.output)}"


class ExcelPage(ToolPage):
    title = "PDF a Excel"
    subtitle = "Pasa las tablas del PDF a una hoja de Excel. Los montos quedan como números para poder sumarlos."
    icon_name = "excel"
    action_text = "Convertir a Excel"
    working_text = "Buscando tablas…"
    modifies = False

    def build_options(self, lay):
        self.pages_option(lay)
        self.borderless = QCheckBox("Buscar también tablas sin bordes (sin líneas)")
        self.borderless.setChecked(True)
        lay.addWidget(self.borderless)
        self.sheets = self.radio_group(lay, [("varias", "Cada tabla en su propia hoja"),
                                             ("una", "Todas las tablas en una sola hoja")])
        return True

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "", ".xlsx", "Libro de Excel (*.xlsx)")
        if not out:
            return None
        return ("mkpdf.core.excel:pdf_to_excel", (src, out),
                {"pages": self.selected_pages(), "borderless": self.borderless.isChecked(),
                 "one_sheet": self.group_value(self.sheets) == "una"}, out)

    def describe(self, r):
        n = r["tables"]
        return (f"Se encontraron {n} tabla{'s' if n != 1 else ''}.\n\n"
                f"Se guardó como: {os.path.basename(self.output)}")


class PowerPointPage(ToolPage):
    title = "PDF a PowerPoint"
    subtitle = ("Convierte cada página en una diapositiva. El texto queda en cuadros que puedes modificar, "
                "en la misma posición del PDF.")
    icon_name = "ppt"
    action_text = "Convertir a PowerPoint"
    working_text = "Creando la presentación…"
    modifies = False

    def build_options(self, lay):
        self.mode = self.radio_group(lay, [
            ("editable", "Texto editable (recomendado)"),
            ("imagen", "Cada página como imagen (idéntica al PDF, sin editar el texto)")])
        self.pages_option(lay)
        return True

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "", ".pptx", "Presentación de PowerPoint (*.pptx)")
        if not out:
            return None
        return ("mkpdf.core.powerpoint:pdf_to_powerpoint", (src, out),
                {"pages": self.selected_pages(), "mode": self.group_value(self.mode)}, out)

    def describe(self, r):
        txt = f"Se crearon {r['pages']} diapositiva{'s' if r['pages'] != 1 else ''}."
        if r.get("scanned"):
            txt += " Las páginas escaneadas se reconocieron con OCR: revisa el texto."
        return txt + f"\n\nSe guardó como: {os.path.basename(self.output)}"


class WordImagesPage(ToolPage):
    title = "Word a imágenes"
    subtitle = ("Guarda cada página de un documento de Word como imagen JPG o PNG, "
                "por ejemplo para publicarla en redes o enviarla por WhatsApp.")
    icon_name = "image"
    kind = "word"
    action_text = "Crear imágenes"
    working_text = "Abriendo el documento con Word…"
    modifies = False

    def build_options(self, lay):
        self.fmt = self.radio_group(lay, [("jpg", "JPG (pesa poco, ideal para enviar)"),
                                          ("png", "PNG (máxima nitidez)")])
        self.dpi = QComboBox()
        for k, t in ((110, "Normal"), (200, "Alta"), (300, "Muy alta (para imprimir)")):
            self.dpi.addItem(t, k)
        self.dpi.setCurrentIndex(1)
        lay.addLayout(_row("Calidad:", self.dpi))
        lay.addWidget(_hint("Se usa el Microsoft Word instalado en esta computadora para respetar el diseño exacto."))
        return True

    def make_task(self):
        src = self.files[0]
        folder = output_folder(self, src)
        if not folder:
            return None
        return ("mkpdf.core.tools:office_to_images", (src, folder),
                {"fmt": self.group_value(self.fmt), "dpi": self.dpi.currentData()}, "")

    def _on_finished(self, r):
        self.output = r["folder"]
        super()._on_finished(r)

    def describe(self, r):
        return f"Se crearon {len(r['files'])} imágenes en la carpeta:\n{os.path.basename(r['folder'])}"


class SearchablePage(ToolPage):
    title = "PDF escaneado a PDF con texto"
    subtitle = ("Reconoce el texto de un PDF escaneado (OCR). El documento se ve igual, pero ahora puedes "
                "buscar palabras, seleccionar y copiar el texto.")
    icon_name = "ocr"
    action_text = "Reconocer texto"
    working_text = "Reconociendo texto…"
    modifies = True

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "con texto", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.searchable:make_searchable", (src, out), {}, out)

    def describe(self, r):
        if not r["ocr_pages"]:
            return ("El PDF ya tenía texto en todas sus páginas, no fue necesario reconocerlo.\n\n"
                    f"Se guardó como: {os.path.basename(self.output)}")
        return (f"Se reconoció el texto de {r['ocr_pages']} página{'s' if r['ocr_pages'] != 1 else ''}.\n\n"
                f"Se guardó como: {os.path.basename(self.output)}")


class ImageTextPage(ToolPage):
    title = "Imagen a texto"
    subtitle = "Saca el texto de una foto, captura de pantalla o imagen escaneada para copiarlo o editarlo en Word."
    icon_name = "imagetext"
    kind = "images"
    action_text = "Sacar el texto"
    working_text = "Reconociendo texto…"
    modifies = False

    def build_options(self, lay):
        self.mode = self.radio_group(lay, [("texto", "Mostrar el texto aquí para copiarlo"),
                                           ("word", "Crear un documento de Word")])
        return True

    def make_task(self):
        src = self.files[0]
        self.text_box.hide()
        if self.group_value(self.mode) == "word":
            out = choose_output(self, src, "", ".docx", "Documento de Word (*.docx)")
            if not out:
                return None
            return ("mkpdf.core.word:image_to_word", (src, out), {}, out)
        return ("mkpdf.core.searchable:image_to_text", (src,), {}, "")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_panel = QFrame()
        self.text_panel.setObjectName("Panel")
        tl = QVBoxLayout(self.text_panel)
        tl.setContentsMargins(16, 14, 16, 14)
        lab = QLabel("Texto reconocido")
        lab.setObjectName("SectionTitle")
        tl.addWidget(lab)
        self.text_box = QPlainTextEdit()
        self.text_box.setMinimumHeight(theme.px(260))
        tl.addWidget(self.text_box)
        row = QHBoxLayout()
        self.copy_btn = icon_button("Copiar todo", "copy", "Primary")
        self.copy_btn.clicked.connect(self._copy)
        self.copied = QLabel("")
        self.copied.setObjectName("Muted")
        row.addWidget(self.copy_btn)
        row.addWidget(self.copied)
        row.addStretch(1)
        tl.addLayout(row)
        self.text_panel.hide()
        self.body.insertWidget(self.body.count() - 1, self.text_panel)

    def _copy(self):
        QGuiApplication.clipboard().setText(self.text_box.toPlainText())
        self.copied.setText("Copiado. Ya puedes pegarlo con Ctrl+V.")

    def _on_finished(self, result):
        if isinstance(result, str):
            self.progress.hide()
            self._update_go()
            self.text_box.show()
            self.text_box.setPlainText(result or "(No se encontró texto en la imagen)")
            self.copied.setText("")
            self.text_panel.show()
            return
        self.text_panel.hide()
        super()._on_finished(result)

    def describe(self, r):
        return f"Se guardó como: {os.path.basename(self.output)}"

    def reset(self):
        super().reset()
        self.text_panel.hide()


# =============================================================================
# HERRAMIENTAS
# =============================================================================

class FolioPage(ToolPage):
    title = "Foliar"
    subtitle = "Numera las hojas del documento en la esquina, como se pide en los expedientes."
    icon_name = "folio"
    action_text = "Foliar documento"
    working_text = "Foliando…"

    POSITIONS = [("sup-der", "Arriba a la derecha"), ("sup-centro", "Arriba al centro"),
                 ("sup-izq", "Arriba a la izquierda"), ("inf-der", "Abajo a la derecha"),
                 ("inf-centro", "Abajo al centro"), ("inf-izq", "Abajo a la izquierda")]

    def build_options(self, lay):
        self.direction = self.radio_group(lay, [
            ("adelante", "De adelante hacia atrás  (la primera hoja es el folio 1)"),
            ("atras", "De atrás hacia adelante  (la última hoja es el folio 1)")], title="Orden de la numeración")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(1, 99999)
        self.start_spin.setValue(1)
        self.pos = QComboBox()
        for k, t in self.POSITIONS:
            self.pos.addItem(t, k)
        self.size = QComboBox()
        for k, t in ((11, "Pequeño"), (14, "Normal"), (18, "Grande"), (24, "Muy grande")):
            self.size.addItem(t, k)
        self.size.setCurrentIndex(1)
        self.prefix = QLineEdit()
        self.prefix.setPlaceholderText("Opcional, por ejemplo: Folio ")
        self.skip = QSpinBox()
        self.skip.setRange(0, 9999)
        grid.addWidget(QLabel("Empezar en el número:"), 0, 0)
        grid.addWidget(self.start_spin, 0, 1)
        grid.addWidget(QLabel("Posición:"), 1, 0)
        grid.addWidget(self.pos, 1, 1)
        grid.addWidget(QLabel("Tamaño del número:"), 2, 0)
        grid.addWidget(self.size, 2, 1)
        grid.addWidget(QLabel("Texto antes del número:"), 3, 0)
        grid.addWidget(self.prefix, 3, 1)
        grid.addWidget(QLabel("No foliar las primeras hojas:"), 4, 0)
        grid.addWidget(self.skip, 4, 1)
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)
        self.box = QCheckBox("Número dentro de un recuadro blanco (se lee mejor sobre el texto)")
        self.box.setChecked(True)
        self.zeros = QCheckBox("Con ceros a la izquierda (0001, 0002…)")
        lay.addWidget(self.box)
        lay.addWidget(self.zeros)
        # vista previa
        pv = QLabel("Vista previa")
        pv.setObjectName("SectionTitle")
        lay.addWidget(pv)
        self.preview_row = QHBoxLayout()
        self.preview_labels = []
        for _ in range(2):
            col = QVBoxLayout()
            img = QLabel()
            img.setAlignment(Qt.AlignCenter)
            img.setMinimumSize(QSize(theme.px(150), theme.px(200)))
            cap = QLabel()
            cap.setObjectName("Muted")
            cap.setAlignment(Qt.AlignCenter)
            col.addWidget(img)
            col.addWidget(cap)
            self.preview_row.addLayout(col)
            self.preview_labels.append((img, cap))
        self.preview_row.addStretch(1)
        lay.addLayout(self.preview_row)
        self._pv_timer = QTimer(self)
        self._pv_timer.setSingleShot(True)
        self._pv_timer.setInterval(250)
        self._pv_timer.timeout.connect(self._preview)
        for w in (self.direction,):
            w.buttonToggled.connect(lambda *a: self._pv_timer.start())
        for w in (self.start_spin, self.skip):
            w.valueChanged.connect(lambda *a: self._pv_timer.start())
        for w in (self.pos, self.size):
            w.currentIndexChanged.connect(lambda *a: self._pv_timer.start())
        self.prefix.textChanged.connect(lambda *a: self._pv_timer.start())
        self.box.toggled.connect(lambda *a: self._pv_timer.start())
        self.zeros.toggled.connect(lambda *a: self._pv_timer.start())
        return True

    def _opts(self):
        return dict(direction=self.group_value(self.direction), start=self.start_spin.value(),
                    position=self.pos.currentData(), size=self.size.currentData(), box=self.box.isChecked(),
                    zeros=4 if self.zeros.isChecked() else 0, prefix=self.prefix.text(), skip=self.skip.value())

    def on_files_changed(self):
        self._pv_timer.start()

    def _preview(self):
        for img, cap in self.preview_labels:
            img.clear()
            cap.clear()
        if not self.files or self.doc_info.get("locked"):
            return
        try:
            from ..core.tools import folio_preview
            shots = folio_preview(self.files[0], dpi=48, **self._opts())
        except Exception:
            return
        for (img, cap), (page_no, folio, png) in zip(self.preview_labels, shots):
            pm = QPixmap()
            pm.loadFromData(png)
            img.setPixmap(pm.scaled(theme.px(170), theme.px(230), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            img.setStyleSheet(f"border: 1px solid {theme.colors()['border']}; background: white;")
            cap.setText(f"Hoja {page_no} → folio {folio}")

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "foliado", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools:foliate", (src, out), self._opts(), out)

    def describe(self, r):
        return (f"Se foliaron {r['pages']} hojas (del folio {r['first']} al {r['last']}).\n\n"
                f"Se guardó como: {os.path.basename(self.output)}")


class A4Page(ToolPage):
    title = "Todas las páginas del mismo tamaño"
    subtitle = ("Deja todas las páginas en A4 (u otro tamaño) con un clic. El contenido se ajusta "
                "sin deformarse y queda centrado.")
    icon_name = "a4"
    action_text = "Igualar tamaño"
    working_text = "Ajustando páginas…"

    def build_options(self, lay):
        self.paper = QComboBox()
        for k, t in (("A4", "A4  (21 × 29,7 cm)"), ("Carta", "Carta  (21,6 × 27,9 cm)"),
                     ("Oficio", "Oficio  (21,6 × 33 cm)"), ("A3", "A3  (29,7 × 42 cm)")):
            self.paper.addItem(t, k)
        lay.addLayout(_row("Tamaño de hoja:", self.paper))
        self.orient = self.radio_group(lay, [
            ("auto", "Las páginas horizontales quedan horizontales"),
            ("vertical", "Todas verticales")])
        self.scale_up = QCheckBox("Agrandar las páginas pequeñas para que llenen la hoja")
        self.scale_up.setChecked(True)
        lay.addWidget(self.scale_up)
        self.margin = QComboBox()
        for k, t in ((0, "Sin margen"), (5, "Margen pequeño (0,5 cm)"), (10, "Margen de 1 cm")):
            self.margin.addItem(t, k)
        lay.addLayout(_row("Margen alrededor:", self.margin))
        return True

    def make_task(self):
        src = self.files[0]
        paper = self.paper.currentData()
        out = choose_output(self, src, paper, ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools:normalize_size", (src, out, paper),
                {"orientation": self.group_value(self.orient), "margin_mm": self.margin.currentData(),
                 "scale_up": self.scale_up.isChecked()}, out)

    def describe(self, r):
        return (f"Listo: {r['pages']} páginas en tamaño {self.paper.currentData()} "
                f"({r['changed']} se ajustaron).\n\nSe guardó como: {os.path.basename(self.output)}")


class MergePage(ToolPage):
    title = "Unir archivos / armar expediente"
    subtitle = ("Junta varios PDF, fotos, documentos de Word y hojas de Excel en un solo PDF, "
                "en el orden que elijas. Arrastra los archivos en la lista para ordenarlos.")
    icon_name = "merge"
    kind = "mixed"
    multi = True
    action_text = "Unir en un solo PDF"
    working_text = "Uniendo archivos…"

    def build_options(self, lay):
        self.all_a4 = QCheckBox("Dejar todas las páginas en tamaño A4")
        self.all_a4.setChecked(False)
        lay.addWidget(self.all_a4)
        lay.addWidget(_hint("Las fotos se colocan en una hoja A4. Los archivos de Word y Excel se convierten "
                            "usando el Microsoft Office instalado en esta computadora."))
        return True

    def make_task(self):
        files = self.flist.files()
        if len(files) < 2 and not any(f.lower().endswith((".doc", ".docx", ".xls", ".xlsx", ".jpg", ".png", ".jpeg")) for f in files):
            inform(self, "Faltan archivos", "Agrega al menos dos archivos para unirlos.")
            return None
        out = choose_output(self, files[0], "unido", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools:merge_files", (files, out), {"fit_all_a4": self.all_a4.isChecked()}, out)

    def describe(self, r):
        return (f"Se unieron {len(self.files)} archivos en un PDF de {r['pages']} páginas.\n\n"
                f"Se guardó como: {os.path.basename(self.output)}")


class SplitPage(ToolPage):
    title = "Dividir PDF"
    subtitle = "Separa un PDF en varios archivos más pequeños."
    icon_name = "split"
    action_text = "Dividir"
    working_text = "Dividiendo…"
    modifies = False

    def build_options(self, lay):
        self.mode = self.radio_group(lay, [("cada", "Cada página en un archivo"),
                                           ("grupos", "En partes de varias páginas"),
                                           ("rangos", "Por rangos que yo escribo")])
        self.every = QSpinBox()
        self.every.setRange(1, 9999)
        self.every.setValue(5)
        lay.addLayout(_row("Páginas por parte:", self.every))
        self.ranges = QLineEdit()
        self.ranges.setPlaceholderText("Ejemplo: 1-3, 4-10, 11-")
        lay.addLayout(_row("Rangos:", self.ranges, stretch=False))
        lay.addWidget(_hint("Los archivos se guardan en una carpeta nueva al lado del original."))
        return True

    def make_task(self):
        src = self.files[0]
        folder = output_folder(self, src)
        if not folder:
            return None
        self._folder_hint = folder
        return ("mkpdf.core.tools:split_pdf", (src, folder),
                {"mode": self.group_value(self.mode), "every": self.every.value(),
                 "ranges_text": self.ranges.text()}, "")

    def _on_finished(self, r):
        self.output = r["folder"]
        super()._on_finished(r)

    def describe(self, r):
        return f"Se crearon {len(r['files'])} archivos en la carpeta:\n{os.path.basename(r['folder'])}"


class CompressPage(ToolPage):
    title = "Comprimir PDF"
    subtitle = "Reduce el peso del archivo, por ejemplo para subirlo a una mesa de partes virtual o enviarlo por correo."
    icon_name = "compress"
    action_text = "Comprimir"
    working_text = "Comprimiendo…"

    def build_options(self, lay):
        self.level = self.radio_group(lay, [
            ("media", "Equilibrado (recomendado)"),
            ("alta", "Máxima compresión (las imágenes pierden algo de calidad)"),
            ("baja", "Ligera (casi sin perder calidad)"),
            ("objetivo", "Que pese menos de:")])
        self.mb = QSpinBox()
        self.mb.setRange(1, 500)
        self.mb.setValue(5)
        self.mb.setSuffix(" MB")
        lay.addLayout(_row("    ", self.mb))
        self.gray = QCheckBox("Pasar las imágenes a escala de grises (pesa todavía menos)")
        lay.addWidget(self.gray)
        return True

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "comprimido", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        lvl = self.group_value(self.level)
        kw = {"level": lvl if lvl != "objetivo" else "media", "grayscale": self.gray.isChecked()}
        if lvl == "objetivo":
            kw["target_mb"] = self.mb.value()
        return ("mkpdf.core.tools:compress_pdf", (src, out), kw, out)

    def describe(self, r):
        if not r["improved"]:
            return ("Este PDF ya estaba optimizado: no se pudo reducir más sin dañarlo. "
                    f"Se guardó una copia igual.\n\nSe guardó como: {os.path.basename(self.output)}")
        pct = 100 - int(100 * r["after"] / max(1, r["before"]))
        txt = f"Antes: {r['before_h']}   →   Ahora: {r['after_h']}  (pesa {pct}% menos)"
        if not r.get("reached"):
            txt += "\n\nNo se llegó al tamaño pedido. Prueba con «Máxima compresión» o divide el documento."
        return txt + f"\n\nSe guardó como: {os.path.basename(self.output)}"


class PhotosPage(ToolPage):
    title = "Fotos a PDF (escáner)"
    subtitle = ("Convierte fotos de documentos tomadas con el celular en un PDF limpio: detecta la hoja, "
                "la endereza y quita las sombras.")
    icon_name = "camera"
    kind = "images"
    multi = True
    action_text = "Crear PDF"
    working_text = "Procesando fotos…"
    modifies = False

    def build_options(self, lay):
        self.mode = self.radio_group(lay, [
            ("color", "Enderezar y limpiar (a color)"),
            ("bn", "Enderezar y limpiar (blanco y negro, como fotocopia)"),
            ("no", "Dejar las fotos tal cual")])
        self.paper = QComboBox()
        self.paper.addItem("A4", "A4")
        self.paper.addItem("Tamaño de la foto", "foto")
        lay.addLayout(_row("Tamaño de hoja:", self.paper))
        return True

    def make_task(self):
        files = self.flist.files()
        out = choose_output(self, files[0], "documento", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools:images_to_pdf", (files, out),
                {"paper": self.paper.currentData(), "scanner": self.group_value(self.mode)}, out)

    def describe(self, r):
        return f"Se creó un PDF de {r['pages']} páginas.\n\nSe guardó como: {os.path.basename(self.output)}"


class ToImagesPage(ToolPage):
    title = "PDF a imágenes"
    subtitle = "Guarda cada página del PDF como una imagen JPG o PNG."
    icon_name = "image"
    action_text = "Crear imágenes"
    working_text = "Creando imágenes…"
    modifies = False

    def build_options(self, lay):
        self.fmt = self.radio_group(lay, [("jpg", "JPG (pesa poco, ideal para enviar)"),
                                          ("png", "PNG (máxima nitidez)")])
        self.dpi = QComboBox()
        for k, t in ((110, "Normal"), (200, "Alta"), (300, "Muy alta (para imprimir)")):
            self.dpi.addItem(t, k)
        self.dpi.setCurrentIndex(1)
        lay.addLayout(_row("Calidad:", self.dpi))
        self.pages_option(lay)
        return True

    def make_task(self):
        src = self.files[0]
        folder = output_folder(self, src)
        if not folder:
            return None
        return ("mkpdf.core.tools:pdf_to_images", (src, folder),
                {"fmt": self.group_value(self.fmt), "dpi": self.dpi.currentData(),
                 "pages": self.selected_pages()}, "")

    def _on_finished(self, r):
        self.output = r["folder"]
        super()._on_finished(r)

    def describe(self, r):
        return f"Se crearon {len(r['files'])} imágenes en la carpeta:\n{os.path.basename(r['folder'])}"


class WatermarkPage(ToolPage):
    title = "Marca de agua"
    subtitle = "Agrega un texto grande y transparente sobre todas las páginas, por ejemplo COPIA o BORRADOR."
    icon_name = "drop"
    action_text = "Agregar marca de agua"
    working_text = "Agregando marca de agua…"

    COLORS = {"gris": (0.55, 0.55, 0.55), "rojo": (0.8, 0.1, 0.1), "azul": (0.1, 0.25, 0.75)}

    def build_options(self, lay):
        self.text = QComboBox()
        self.text.setEditable(True)
        self.text.addItems(["COPIA", "BORRADOR", "CONFIDENCIAL", "ANULADO", "NO VÁLIDO", "COPIA CONTROLADA"])
        lay.addLayout(_row("Texto:", self.text))
        self.color = QComboBox()
        for k, t in (("gris", "Gris"), ("rojo", "Rojo"), ("azul", "Azul")):
            self.color.addItem(t, k)
        lay.addLayout(_row("Color:", self.color))
        self.strength = QComboBox()
        for k, t in ((0.15, "Suave"), (0.25, "Normal"), (0.4, "Fuerte")):
            self.strength.addItem(t, k)
        self.strength.setCurrentIndex(1)
        lay.addLayout(_row("Intensidad:", self.strength))
        self.diag = QCheckBox("En diagonal")
        self.diag.setChecked(True)
        lay.addWidget(self.diag)
        return True

    def make_task(self):
        src = self.files[0]
        text = self.text.currentText().strip()
        if not text:
            inform(self, "Falta el texto", "Escribe el texto de la marca de agua.")
            return None
        out = choose_output(self, src, "con marca", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools:watermark", (src, out),
                {"text": text, "color": self.COLORS[self.color.currentData()],
                 "opacity": self.strength.currentData(), "diagonal": self.diag.isChecked()}, out)

    def describe(self, r):
        return f"Se guardó como: {os.path.basename(self.output)}"


class PasswordPage(ToolPage):
    title = "Contraseña"
    subtitle = "Protege un PDF con contraseña para que solo lo abran quienes la conozcan, o quítale la contraseña."
    icon_name = "lock"
    action_text = "Aplicar"
    working_text = "Guardando…"
    modifies = False

    def build_options(self, lay):
        self.mode = self.radio_group(lay, [("poner", "Ponerle contraseña"), ("quitar", "Quitarle la contraseña")])
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("Contraseña")
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.Password)
        self.pw2.setPlaceholderText("Repite la contraseña")
        lay.addLayout(_row("Contraseña:", self.pw, stretch=False))
        self.pw2_row = _row("Repetir:", self.pw2, stretch=False)
        lay.addLayout(self.pw2_row)
        self.show_pw = QCheckBox("Mostrar lo que escribo")
        self.show_pw.toggled.connect(lambda on: [w.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
                                                 for w in (self.pw, self.pw2)])
        lay.addWidget(self.show_pw)
        lay.addWidget(_hint("Anota la contraseña en un lugar seguro: si se olvida, no se puede recuperar."))
        self.mode.buttonToggled.connect(lambda *a: self.pw2.setEnabled(self.group_value(self.mode) == "poner"))
        return True

    def on_files_changed(self):
        if self.doc_info.get("locked"):
            self.mode.button(1).setChecked(True)
            self.banner.hide()
        self.go.setEnabled(bool(self.files))

    def _update_go(self):
        self.go.setEnabled(bool(self.files) and not self.runner.running())

    def make_task(self):
        src = self.files[0]
        mode = self.group_value(self.mode)
        if mode == "poner":
            if not self.pw.text():
                inform(self, "Falta la contraseña", "Escribe una contraseña.")
                return None
            if self.pw.text() != self.pw2.text():
                inform(self, "No coinciden", "Las dos contraseñas no son iguales. Escríbelas de nuevo.")
                return None
            out = choose_output(self, src, "protegido", ".pdf", "PDF (*.pdf)")
            if not out:
                return None
            return ("mkpdf.core.tools_tasks:protect_task", (src, out, self.pw.text()), {}, out)
        out = choose_output(self, src, "sin contraseña", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools_tasks:unprotect_task", (src, out, self.pw.text()), {}, out)

    def describe(self, r):
        return f"Se guardó como: {os.path.basename(self.output)}"


class CleanPage(ToolPage):
    title = "Limpiar escaneo"
    subtitle = "Arregla documentos escaneados: quita hojas en blanco, gira las que están de cabeza y endereza las torcidas."
    icon_name = "clean"
    action_text = "Limpiar"
    working_text = "Revisando páginas…"

    def build_options(self, lay):
        self.blank = QCheckBox("Quitar las hojas en blanco")
        self.rot = QCheckBox("Girar las hojas que están de cabeza o de costado")
        self.skew = QCheckBox("Enderezar las hojas torcidas")
        for c in (self.blank, self.rot, self.skew):
            c.setChecked(True)
            lay.addWidget(c)
        return True

    def make_task(self):
        src = self.files[0]
        out = choose_output(self, src, "limpio", ".pdf", "PDF (*.pdf)")
        if not out:
            return None
        return ("mkpdf.core.tools:clean_scan", (src, out),
                {"remove_blank": self.blank.isChecked(), "fix_orientation": self.rot.isChecked(),
                 "deskew": self.skew.isChecked()}, out)

    def describe(self, r):
        parts = []
        if r["removed"]:
            parts.append(f"se quitaron {r['removed']} hojas en blanco")
        if r["rotated"]:
            parts.append(f"se giraron {r['rotated']}")
        if r["straightened"]:
            parts.append(f"se enderezaron {r['straightened']}")
        txt = ("Listo: " + ", ".join(parts) + ".") if parts else "No se encontró nada que corregir."
        return txt + f"\n\nSe guardó como: {os.path.basename(self.output)}"


class SearchPage(ToolPage):
    title = "Buscar en una carpeta"
    subtitle = "Escribe una palabra o frase y encuentra en qué PDF y en qué página aparece."
    icon_name = "search"
    action_text = "Buscar"
    working_text = "Buscando…"
    needs_file = False
    modifies = False

    def build_options(self, lay):
        self.folder = QLineEdit()
        self.folder.setPlaceholderText("Elige la carpeta donde buscar")
        self.folder.setReadOnly(True)
        pick = icon_button("Elegir carpeta", "folder")
        pick.clicked.connect(self._pick)
        lay.addLayout(_row("Carpeta:", self.folder, pick, stretch=False))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Por ejemplo: resolución de alcaldía")
        self.query.returnPressed.connect(self.start)
        lay.addLayout(_row("Buscar:", self.query, stretch=False))
        self.sub = QCheckBox("Buscar también dentro de las subcarpetas")
        self.sub.setChecked(True)
        lay.addWidget(self.sub)
        lay.addWidget(_hint("No importa si escribes con o sin tildes, ni mayúsculas."))
        return True

    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = QListWidget()
        self.results.setMinimumHeight(theme.px(260))
        self.results.setWordWrap(True)
        self.results.itemDoubleClicked.connect(lambda it: open_path(it.data(Qt.UserRole)))
        self.results.hide()
        self.res_hint = _hint("Haz doble clic en un resultado para abrir el archivo.")
        self.res_hint.hide()
        self.body.insertWidget(self.body.count() - 1, self.res_hint)
        self.body.insertWidget(self.body.count() - 1, self.results)

    def _pick(self):
        from ..config import settings
        d = QFileDialog.getExistingDirectory(self, "Carpeta donde buscar", settings().get("last_dir") or os.path.expanduser("~"))
        if d:
            self.folder.setText(d)

    def _update_go(self):
        self.go.setEnabled(not self.runner.running())

    def make_task(self):
        if not self.folder.text():
            inform(self, "Falta la carpeta", "Elige la carpeta donde quieres buscar.")
            return None
        if not self.query.text().strip():
            inform(self, "Falta la palabra", "Escribe la palabra o frase que quieres buscar.")
            return None
        self.results.clear()
        self.results.hide()
        return ("mkpdf.core.tools:search_folder", (self.folder.text(), self.query.text()),
                {"subfolders": self.sub.isChecked()}, "")

    def _on_finished(self, r):
        self.progress.hide()
        self._update_go()
        self.results.clear()
        for item in r["results"]:
            it = QListWidgetItem(f"{os.path.basename(item['file'])}  —  página {item['page']}\n{item['snippet']}")
            it.setData(Qt.UserRole, item["file"])
            it.setToolTip(item["file"])
            self.results.addItem(it)
        n = len(r["results"])
        msg = (f"Se encontraron {n} resultado{'s' if n != 1 else ''} en {r['searched']} PDF revisados."
               if n else f"No se encontró la búsqueda en los {r['searched']} PDF revisados.")
        if r["no_text"]:
            msg += (f"\n{len(r['no_text'])} PDF son escaneados sin texto y no se pudieron revisar. "
                    "Pásalos por «PDF escaneado a PDF con texto» para poder buscar en ellos.")
        self.result.show_result("", msg, title="Búsqueda terminada")
        self.results.setVisible(bool(n))
        self.res_hint.setVisible(bool(n))
