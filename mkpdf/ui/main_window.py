"""Ventana principal con pestañas."""
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget, QApplication)

from . import icons, pages, theme
from .dialogs import AboutDialog, SettingsDialog
from .editor import EditorTab
from .organize import OrganizeTab
from .updater import UpdateBar, UpdateChecker, UpdateDialog
from .widgets import Card, IconLabel, icon_button, refresh_button_icons
from ..config import APP_EDITION, APP_NAME, APP_VERSION, COMPANY, DEVELOPER, settings


class CardHome(QStackedWidget):
    """Pantalla con tarjetas; al hacer clic se abre la herramienta."""

    def __init__(self, title, subtitle, items, columns=2, parent=None):
        super().__init__(parent)
        self.items = items
        self.columns = columns
        self.pages = {}
        home = QWidget()
        home.setObjectName("Page")
        outer = QVBoxLayout(home)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        inner = QWidget()
        inner.setObjectName("Page")
        scroll.setWidget(inner)
        center = QHBoxLayout(inner)
        center.setContentsMargins(24, 18, 24, 24)
        content = QWidget()
        content.setMaximumWidth(1180)
        center.addStretch(1)
        center.addWidget(content, 100)
        center.addStretch(1)
        lay = QVBoxLayout(content)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        s = QLabel(subtitle)
        s.setObjectName("Muted")
        s.setWordWrap(True)
        lay.addWidget(s)
        lay.addSpacing(12)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        lay.addLayout(self.grid)
        lay.addStretch(1)
        self.cards = []
        for key, icon_name, ctitle, ctext, cls in items:
            card = Card(icon_name, ctitle, ctext)
            card.clicked.connect(lambda k=key, c=cls: self.open_tool(k, c))
            self.cards.append(card)
        self._layout_cards(columns)
        self.addWidget(home)

    def _layout_cards(self, cols):
        for c in self.cards:
            self.grid.removeWidget(c)
        for i, c in enumerate(self.cards):
            self.grid.addWidget(c, i // cols, i % cols)
        for col in range(3):
            self.grid.setColumnStretch(col, 1 if col < cols else 0)
        self.columns = cols

    def resizeEvent(self, e):
        super().resizeEvent(e)
        want = 3 if (len(self.cards) > 4 and self.width() > theme.px(1060)) else 2
        if self.width() < theme.px(640):
            want = 1
        if want != self.columns:
            self._layout_cards(want)

    def open_tool(self, key, cls):
        page = self.pages.get(key)
        if page is None:
            page = cls()
            page.backRequested.connect(lambda: self.setCurrentIndex(0))
            self.pages[key] = page
            self.addWidget(page)
        self.setCurrentWidget(page)

    def refresh(self):
        for c in self.cards:
            c.refresh()


CONVERT_ITEMS = [
    ("word", "word", "PDF a Word", "Para editar el documento. Respeta márgenes, tablas e imágenes. "
     "Sirve también con PDF escaneados.", pages.WordPage),
    ("excel", "excel", "PDF a Excel", "Pasa las tablas a una hoja de cálculo, con los montos listos para sumar.",
     pages.ExcelPage),
    ("ppt", "ppt", "PDF a PowerPoint", "Cada página como diapositiva, con el texto editable.", pages.PowerPointPage),
    ("ocr", "ocr", "PDF escaneado a PDF con texto", "Reconoce el texto (OCR) para poder buscar y copiar.",
     pages.SearchablePage),
    ("imgtxt", "imagetext", "Imagen a texto", "Saca el texto de una foto o captura de pantalla.",
     pages.ImageTextPage),
    ("toimg", "pdfimg", "PDF a imágenes", "Guarda cada página del PDF como imagen JPG o PNG.", pages.ToImagesPage),
    ("wordimg", "wordimg", "Word a imágenes", "Guarda cada página de un Word como imagen JPG o PNG.",
     pages.WordImagesPage),
]

TOOLS_ITEMS = [
    ("folio", "folio", "Foliar", "Numera las hojas, de adelante hacia atrás o de atrás hacia adelante.", pages.FolioPage),
    ("a4", "a4", "Todas a tamaño A4", "Iguala el tamaño de todas las páginas con un clic.", pages.A4Page),
    ("merge", "merge", "Unir / armar expediente", "Junta PDF, fotos, Word y Excel en un solo PDF.", pages.MergePage),
    ("split", "split", "Dividir PDF", "Separa un PDF en varios archivos.", pages.SplitPage),
    ("compress", "compress", "Comprimir PDF", "Reduce el peso para enviarlo o subirlo a una mesa de partes.",
     pages.CompressPage),
    ("photos", "camera", "Fotos a PDF (escáner)", "Convierte fotos del celular en un documento limpio.",
     pages.PhotosPage),
    ("water", "drop", "Marca de agua", "Agrega COPIA, BORRADOR u otro texto sobre las páginas.", pages.WatermarkPage),
    ("pass", "lock", "Contraseña", "Pon o quita la contraseña de un PDF.", pages.PasswordPage),
    ("clean", "clean", "Limpiar escaneo", "Quita hojas en blanco, gira y endereza páginas escaneadas.",
     pages.CleanPage),
    ("search", "search", "Buscar en una carpeta", "Encuentra en qué PDF aparece una palabra.", pages.SearchPage),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(theme.px(1120), theme.px(780))
        self.setMinimumSize(QSize(860, 600))

        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- encabezado ---
        header = QWidget()
        header.setObjectName("Header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 10, 16, 0)
        hl.setSpacing(12)
        self.logo = QLabel()
        self.logo.setPixmap(icons.logo_pixmap(theme.px(40)))
        hl.addWidget(self.logo, 0, Qt.AlignVCenter)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        name = QLabel(APP_NAME)
        name.setObjectName("AppTitle")
        sub = QLabel("Convierte, edita y ordena tus PDF")
        sub.setObjectName("AppSubtitle")
        tcol.addWidget(name)
        tcol.addWidget(sub)
        self.subtitle = sub
        hl.addLayout(tcol)
        hl.addSpacing(24)

        self.tab_group = QButtonGroup(self)
        self.tab_group.setExclusive(True)
        for i, (text, icon_name) in enumerate((("Convertir", "word"), ("Editar PDF", "editpdf"),
                                              ("Organizar páginas", "pages"), ("Herramientas", "tools"))):
            b = QPushButton(text)
            b.setObjectName("TabButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.tab_group.addButton(b, i)
            hl.addWidget(b, 0, Qt.AlignBottom)
        hl.addStretch(1)
        self.settings_btn = icon_button("Ajustes", "settings", "HeaderButton")
        self.about_btn = icon_button("Acerca de", "info", "HeaderButton")
        self.settings_btn.clicked.connect(self.open_settings)
        self.about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        hl.addWidget(self.settings_btn, 0, Qt.AlignVCenter)
        hl.addWidget(self.about_btn, 0, Qt.AlignVCenter)
        lay.addWidget(header)
        self.update_bar = UpdateBar()
        self.update_bar.update_btn.clicked.connect(self._open_update)
        self.update_bar.notes_btn.clicked.connect(self._open_update)
        lay.addWidget(self.update_bar)

        # --- contenido ---
        self.stack = QStackedWidget()
        self.convert = CardHome("¿Qué quieres convertir?",
                                "Elige una opción. Todo se hace en tu computadora, sin internet.",
                                CONVERT_ITEMS, columns=2)
        self.editor = EditorTab()
        self.organize = OrganizeTab()
        self.tools = CardHome("Herramientas de oficina",
                              "Elige lo que necesitas hacer con tus documentos.", TOOLS_ITEMS, columns=3)
        for w in (self.convert, self.editor, self.organize, self.tools):
            self.stack.addWidget(w)
        lay.addWidget(self.stack, 1)
        self.tab_group.idClicked.connect(self._switch)
        self.tab_group.button(0).setChecked(True)

        # --- pie ---
        footer = QWidget()
        footer.setObjectName("Footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(20, 6, 20, 6)
        dev = QLabel(f"Desarrollado por {DEVELOPER}  ·  {COMPANY}")
        dev.setObjectName("FooterText")
        ver = QLabel(f"Versión {APP_VERSION}  ·  Funciona sin internet")
        ver.setObjectName("FooterText")
        fl.addWidget(dev)
        fl.addStretch(1)
        fl.addWidget(ver)
        lay.addWidget(footer)

    def _switch(self, i):
        self.stack.setCurrentIndex(i)

    def start_update_check(self):
        if not settings().get("check_updates"):
            return
        self.checker = UpdateChecker(self)
        self.checker.found.connect(self.update_bar.show_info)
        QTimer.singleShot(3000, self.checker.check)

    def _open_update(self):
        if self.update_bar.info:
            UpdateDialog(self.update_bar.info, self).exec()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.subtitle.setVisible(self.width() >= theme.px(1180))

    def closeEvent(self, e):
        if self.editor.has_unsaved():
            from .widgets import ask
            if not ask(self, "Cambios sin guardar", "En «Editar PDF» hay cambios sin guardar.\n"
                       "¿Quieres cerrar el programa de todas formas?", "Cerrar sin guardar", "Volver"):
                self.tab_group.button(1).setChecked(True)
                self._switch(1)
                e.ignore()
                return
        e.accept()

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.appearanceChanged.connect(self.apply_appearance)
        dlg.exec()
        self.apply_appearance()

    def apply_appearance(self):
        st = settings()
        theme.apply(QApplication.instance(), st.get("theme"), st.get("text_scale"))
        self.convert.refresh()
        self.tools.refresh()
        self.editor.refresh_theme()
        self.update_bar.restyle()
        refresh_button_icons(self)
        self.logo.setPixmap(icons.logo_pixmap(theme.px(40)))
        for w in self.findChildren(IconLabel):
            w.refresh()
