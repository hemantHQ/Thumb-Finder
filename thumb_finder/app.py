from collections import OrderedDict
from dataclasses import replace
from functools import partial
from pathlib import Path
from threading import Event
import os

import requests
from PIL import Image, ImageOps
from PySide6.QtCore import (QEasingCurve, QObject, QPoint, QRect, QRunnable, QSettings,
                            QSize, QStandardPaths, Qt, QThreadPool, QTimer, QUrl, QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QDesktopServices, QIcon, QImage, QPainter, QPen, QPixmap, QPolygon)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGraphicsOpacityEffect,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import VERSION
from . import comfy, offline, services, studio
from .youtube import REPOSITORY, YouTube, distance, signature, thumbnail, video_id

PATHS = {
    "logo": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>',
    "search": '<circle cx="10.5" cy="10.5" r="5.5"/><path d="m15 15 4 4"/>',
    "create": '<path d="M12 2l2.5 7.5L22 12l-7.5 2.5L12 22l-2.5-7.5L2 12l7.5-2.5z"/>',
    "edit": '<path d="m4 16-1 5 5-1L20 8l-4-4zM13 7l4 4"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="9" r="1"/><path d="m4 17 5-4 4 3 4-5 4 4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    "moon": '<path d="M20.5 14.7A8.7 8.7 0 0 1 9.3 3.5 8.8 8.8 0 1 0 20.5 14.7Z"/>',
    "settings": '<path d="M4 6h16M4 12h16M4 18h16"/><path stroke-width="4" d="M9 6h.1m6 6h.1M8 18h.1"/>',
    "update": '<path d="M20 8A8.5 8.5 0 0 0 5 6L3 9m0-5v5h5m-4 7a8.5 8.5 0 0 0 15 2l2-3m0 5v-5h-5"/>',
    "save": '<path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/>',
    "watch": '<path d="m8 5 11 7-11 7z"/>',
}


def icon(name, color="#9ca3b6", size=24):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           f'{PATHS[name]}</svg>')
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    return QIcon(pixmap)


def label(text, style=""):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(style)
    return widget


def button(text, callback, style="", glyph=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setObjectName(style)
    widget.clicked.connect(callback)
    if glyph:
        widget.setProperty("glyph", glyph)
    return widget


def panel(style="surface"):
    widget = QFrame()
    widget.setObjectName(style)
    return widget


def row(*widgets):
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


class TaskSignals(QObject):
    done = Signal(object, object)


class Task(QRunnable):
    def __init__(self, action):
        super().__init__()
        self.action = action
        self.signals = TaskSignals()

    def run(self):
        try:
            result = self.action()
        except Exception as error:
            self.signals.done.emit(None, str(error) or type(error).__name__)
        else:
            self.signals.done.emit(result, None)


class Picture(QWidget):
    selected = Signal(object)

    def __init__(self, height=130):
        super().__init__()
        self.setMinimumHeight(height)
        self.pixmap = QPixmap()
        self.mask_preview = QImage()
        self.placeholder = "No image"
        self.selectable = False
        self.selection_mode = "box"
        self.brush = 0.035
        self.stroke = []
        self.canvas_color = QColor("#ebe8f3")
        self.text_color = QColor("#625d78")
        self.start = self.end = None

    def set_data(self, data, placeholder=None):
        self.pixmap = QPixmap.fromImage(data) if isinstance(data, QImage) else QPixmap()
        if placeholder is not None:
            self.placeholder = placeholder
        self.update()

    def image_rect(self):
        if self.pixmap.isNull():
            return QRect()
        size = self.pixmap.size().scaled(self.size() - QSize(8, 8), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(QPoint((self.width() - size.width()) // 2, (self.height() - size.height()) // 2), size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.canvas_color)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 9, 9)
        if self.pixmap.isNull():
            painter.setPen(self.text_color)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)
        else:
            bounds = self.image_rect()
            painter.drawPixmap(bounds, self.pixmap)
            painter.setClipRect(bounds)
            if not self.mask_preview.isNull():
                painter.drawImage(bounds, self.mask_preview)
        if self.selection_mode == "brush" and self.stroke:
            pen = QPen(QColor(175, 145, 255, 165), max(2, round(self.image_rect().width() * self.brush)))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            if len(self.stroke) == 1:
                painter.drawPoint(self.stroke[0])
            else:
                painter.drawPolyline(QPolygon(self.stroke))
        elif self.start is not None and self.end is not None:
            painter.setPen(QPen(QColor("#a89cff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(145, 122, 255, 48))
            painter.drawRect(QRect(self.start, self.end).normalized())

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        if self.selectable and event.button() == Qt.MouseButton.LeftButton and self.image_rect().contains(point):
            self.start = self.end = point
            self.stroke = [point] if self.selection_mode == "brush" else []
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            bounds = self.image_rect()
            point = event.position().toPoint()
            self.end = QPoint(max(bounds.left(), min(bounds.right(), point.x())),
                              max(bounds.top(), min(bounds.bottom(), point.y())))
            if self.stroke and self.end != self.stroke[-1]:
                self.stroke.append(self.end)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        self.mouseMoveEvent(event)
        selection = QRect(self.start, self.end).normalized()
        bounds = self.image_rect()
        points = self.stroke or [selection.topLeft(), selection.bottomRight()]
        self.start = self.end = None
        self.stroke = []
        self.update()
        if self.selection_mode == "brush" or (selection.width() > 5 and selection.height() > 5):
            self.selected.emit((self.selection_mode,
                                [(float(point.x() - bounds.left()) / bounds.width(),
                                  float(point.y() - bounds.top()) / bounds.height()) for point in points],
                                self.brush))


class ThemeSwitch(QPushButton):
    def __init__(self, dark, callback):
        super().__init__()
        self.setFixedSize(64, 34)
        self.setAccessibleName("Toggle light and dark theme")
        self.setToolTip("Toggle light and dark theme")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.position = float(dark)
        self.animation = QVariantAnimation(self, duration=180)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.move_thumb)
        self.clicked.connect(callback)

    def move_thumb(self, value):
        self.position = value
        self.update()

    def animate(self, dark):
        self.animation.stop()
        self.animation.setStartValue(self.position)
        self.animation.setEndValue(float(dark))
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = self.position >= 0.5
        painter.setPen(QPen(QColor("#41415a" if dark else "#ccc7e2")))
        painter.setBrush(QColor("#252537" if dark else "#e8e4f6"))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#6753cf" if dark else "#ffffff"))
        painter.drawEllipse(5 + round(29 * self.position), 5, 24, 24)
        icon("sun", "#b4adcf" if dark else "#5645ad").paint(painter, 10, 10, 14, 14)
        icon("moon", "#ffffff" if dark else "#665d82").paint(painter, 39, 10, 14, 14)


class Window(QMainWindow):
    offline_progress = Signal(str)
    draft_ready = Signal(object, int)

    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.dark = self.settings.value("dark", QApplication.styleHints().colorScheme() ==
                                        Qt.ColorScheme.Dark, type=bool)
        self.create_stop = Event()
        self.stop_batch = Event()
        self.create_paths = ["", ""]
        self.create_outputs = []
        self.offline_busy = False
        self.downloading = False
        self.remove_selections = []
        self.offline_stop = Event()
        data_root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.history_root = data_root / "Drafts"
        self.model_root = data_root / "Models"
        self.youtube = self.make_youtube()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.search_pool = QThreadPool(self)
        self.search_pool.setMaxThreadCount(1)
        self.image_pool = QThreadPool(self)
        self.image_pool.setMaxThreadCount(5)
        self.tasks = set()
        self.results = {}
        self.cards = {}
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.search_generation = 0
        self.searching = False
        self.next_token = None
        self.empty_pages = 0
        self.reference = None
        self.rank = {}
        self.rank_timer = QTimer(self, interval=90, singleShot=True)
        self.rank_timer.timeout.connect(self.arrange_cards)
        self.columns = None
        self.candidates = [studio.Candidate() for _ in "ABC"]
        self.active = 0
        self.preview_revision = [0, 0, 0]
        self.preview_busy = False
        self.preview_dirty = set()
        self.preview_timer = QTimer(self, interval=55, singleShot=True)
        self.preview_timer.timeout.connect(self.update_previews)
        self.setWindowTitle(f"Thumb Finder v{VERSION}")
        app_icon = QIcon(str(Path(__file__).with_name("app_icon.svg")))
        QApplication.instance().setWindowIcon(app_icon)
        self.setWindowIcon(app_icon)
        self.resize(1240, 865)
        self.setMinimumSize(875, 680)

        body = QWidget()
        body.setObjectName("body")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(26, 16, 26, 14)
        layout.setSpacing(15)
        logo = label("")
        logo.setPixmap(app_icon.pixmap(42, 42))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(42, 42)
        name = label("Thumb Finder", "brand")
        version = label(f"v{VERSION}", "muted")
        header = row(logo, name, version)
        header.setSpacing(10)
        header.addStretch()
        nav = panel("nav")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(4, 4, 4, 4)
        nav_layout.setSpacing(3)
        self.nav = []
        for index, (title, glyph) in enumerate(zip(("Search", "Create", "Edit"), ("search", "create", "edit"))):
            item = button(title, partial(self.show_page, index), "tab", glyph)
            item.setCheckable(True)
            nav_layout.addWidget(item)
            self.nav.append(item)
        header.addWidget(nav)
        header.addStretch()
        self.theme = ThemeSwitch(self.dark, self.toggle_theme)
        header.addWidget(self.theme)
        update = button("Updates", self.check_updates, "", "update")
        update.setToolTip("Check for updates")
        header.addWidget(update)
        header.addWidget(button("Settings", self.open_settings, "", "settings"))
        layout.addLayout(header)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self.pages.addWidget(self.build_search())
        self.pages.addWidget(self.build_create())
        self.pages.addWidget(self.build_editor())
        self.footer = label("Ready", "muted")
        footer = row(self.footer)
        self.footer.setMinimumWidth(0)
        self.footer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.setStretch(0, 1)
        footer.addWidget(label("Thumb Finder by Hemant", "credit"))
        layout.addLayout(footer)
        self.setCentralWidget(body)
        self.offline_progress.connect(self.notice, Qt.ConnectionType.QueuedConnection)
        self.draft_ready.connect(self.show_generation_progress, Qt.ConnectionType.QueuedConnection)
        self.apply_theme()
        self.show_page(0)
        self.sync_editor()

    def make_youtube(self):
        try:
            from ._build_keys import KEYS
        except ImportError:
            KEYS = ("", "")
        return YouTube(self.settings.value(f"youtube/key{index}", "", type=str).strip()
                       or os.environ.get(f"YOUTUBE_API_KEY_{index}", "").strip() or KEYS[index - 1]
                       for index in (1, 2))

    def task(self, action, callback, pool=None):
        task = Task(action)
        task.is_search = pool in (self.image_pool, self.search_pool)
        self.tasks.add(task)

        def finished(result, error):
            self.tasks.discard(task)
            callback(result, error)

        task.signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
        (pool or self.pool).start(task)

    def notice(self, text):
        self.footer.setText(text)

    def show_page(self, index):
        old = self.pages.currentWidget()
        if old and old.graphicsEffect():
            old.setGraphicsEffect(None)
        self.pages.setCurrentIndex(index)
        for position, item in enumerate(self.nav):
            item.setChecked(position == index)
        widget = self.pages.currentWidget()
        effect = QGraphicsOpacityEffect(widget, opacity=0.82)
        widget.setGraphicsEffect(effect)
        self.fade = QVariantAnimation(effect, duration=145)
        self.fade.setStartValue(0.82)
        self.fade.setEndValue(1.0)
        self.fade.valueChanged.connect(effect.setOpacity)
        self.fade.finished.connect(lambda: widget.setGraphicsEffect(None))
        self.fade.start()

    def toggle_theme(self):
        self.dark = not self.dark
        self.settings.setValue("dark", self.dark)
        self.theme.animate(self.dark)
        self.apply_theme()

    def apply_theme(self):
        bg, surface, sub, border, ink, muted, accent, hover = (
            ("#12131b", "#1c1e2a", "#151722", "#303344", "#f3f3fc", "#afb3cc", "#a99bff", "#2c2d44")
            if self.dark else
            ("#f2f1f8", "#ffffff", "#f5f3fb", "#dedbeb", "#242238", "#625d78", "#5741c5", "#ece7fa")
        )
        self.ink = ink
        self.canvas_color, self.muted = sub, muted
        chevron = Path(__file__).with_name("chevron.svg").as_posix()
        self.setStyleSheet(f"""
            QWidget {{font-size: 13px; color: {ink};}}
            QMainWindow, QWidget#body, QScrollArea, QWidget#scrollBody, QStackedWidget {{ background: {bg}; }}
            QFrame#surface, QFrame#nav {{background: {surface}; border: 1px solid {border}; border-radius: 14px;}}
            QFrame#picked {{background: {surface}; border: 2px solid {accent}; border-radius: 14px;}}
            QLabel#brand {{font-size: 19px; font-weight: 750;}}
            QLabel#hero {{font-size: 34px; font-weight: 750;}}
            QLabel#heading {{font-size: 22px; font-weight: 700;}}
            QLabel#strong {{font-size: 14px; font-weight: 700;}}
            QLabel#muted {{color: {muted};}}
            QLabel#credit {{color: {muted}; font-size: 11px;}}
            QLabel#accent {{color: {accent}; font-weight: 700;}}
            QPushButton, QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
                background: {sub}; border: 1px solid {border}; border-radius: 8px; padding: 7px 10px;
            }}
            QPushButton:hover, QComboBox:hover {{background: {hover}; }}
            QPushButton:pressed {{border-color: {accent};}}
            QPushButton:disabled {{color: {muted}; background: {sub};}}
            QPushButton#tab {{border-color: transparent; background: transparent; padding: 8px 14px;}}
            QPushButton#tab:hover, QPushButton#tab:checked {{background: {hover}; color: {accent};}}
            QPushButton:checked {{border-color: {accent};}}
            QPushButton#primary {{background: #5944ca; color: white; font-weight: 700; border-color: #5944ca;}}
            QPushButton#primary:hover {{background: #6953da;}}
            QPushButton#primary:disabled {{background: {sub}; color: {muted}; border-color: {border};}}
            QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus {{border-color: {accent};}}
            QComboBox QAbstractItemView {{background: {surface}; selection-background-color: #5944ca; selection-color: white;}}
            QComboBox {{padding-right: 22px;}}
            QComboBox::drop-down {{subcontrol-origin: border; subcontrol-position: center right; width: 24px; border: 0; background: transparent;}}
            QComboBox::down-arrow {{image: url("{chevron}"); width: 16px; height: 16px;}}
            QScrollArea {{border: 0;}}
            QScrollBar:vertical {{background: {sub}; width: 9px; margin: 0;}}
            QScrollBar::handle:vertical {{background: {muted}; border-radius: 4px; min-height: 32px;}}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{height: 0;}}
            QSlider::groove:horizontal {{height: 4px; background: {border}; border-radius: 2px;}}
            QSlider::handle:horizontal {{background: {accent}; width: 13px; margin: -5px 0; border-radius: 6px;}}
            QToolTip, QDialog, QMessageBox {{background: {surface}; color: {ink};}}
        """)
        for widget in self.findChildren(QPushButton):
            self.decorate(widget)
        for widget in self.findChildren(Picture):
            self.decorate_picture(widget)

    def decorate_picture(self, picture):
        picture.canvas_color = QColor(self.canvas_color)
        picture.text_color = QColor(self.muted)
        picture.update()

    def decorate(self, widget):
        glyph = widget.property("glyph")
        if glyph:
            widget.setIcon(icon(glyph, "#ffffff" if widget.objectName() == "primary" else self.ink))
            widget.setIconSize(QSize(17, 17))

    def build_search(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        hero = panel()
        contents = QVBoxLayout(hero)
        contents.setContentsMargins(22, 16, 22, 16)
        contents.addWidget(label("Find your next thumbnail", "hero"))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Movie title, actor name or YouTube URL")
        self.query.clearButtonEnabled = True
        self.query.returnPressed.connect(self.start_search)
        self.search_button = button("Search", self.start_search, "primary", "search")
        search = row(self.query, self.search_button)
        search.setStretch(0, 1)
        contents.addLayout(search)
        self.genre = QComboBox()
        self.genre.addItems(["Category", "Action", "Comedy", "Drama", "Horror", "Romance", "Thriller", "Western"])
        self.genre.setAccessibleName("Category")
        self.genre.setMinimumWidth(135)
        self.reference_button = button("Reference image", self.pick_reference, "", "image")
        self.clear_reference = button("Clear", self.remove_reference)
        self.clear_reference.hide()
        filters = row(self.genre, self.reference_button, self.clear_reference)
        filters.addStretch()
        contents.addLayout(filters)
        layout.addWidget(hero)
        self.results_label = label("Results", "heading")
        self.sort_label = label("By views", "muted")
        self.sort_label.setToolTip("Sorts the fetched results only.")
        self.sort_label.hide()
        heading = row(self.results_label)
        heading.addStretch()
        heading.addWidget(self.sort_label)
        layout.addLayout(heading)
        self.result_scroll = QScrollArea()
        self.result_scroll.setWidgetResizable(True)
        self.result_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.result_scroll.verticalScrollBar().valueChanged.connect(self.check_scroll)
        self.result_body = QWidget(objectName="scrollBody")
        self.result_layout = QVBoxLayout(self.result_body)
        self.result_layout.setContentsMargins(0, 0, 8, 0)
        self.results_grid = QGridLayout()
        self.results_grid.setSpacing(12)
        self.result_layout.addLayout(self.results_grid)
        self.empty = label("Search YouTube for movie thumbnails", "muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_layout.addWidget(self.empty, 1)
        self.more = button("Load more", self.load_more)
        self.more.hide()
        self.result_layout.addWidget(self.more)
        self.result_layout.addStretch()
        self.result_scroll.setWidget(self.result_body)
        layout.addWidget(self.result_scroll, 1)
        return page

    def build_create(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        composer = panel()
        form = QVBoxLayout(composer)
        form.setContentsMargins(20, 16, 20, 16)
        title = row(label("Create a thumbnail", "heading"))
        title.addStretch()
        self.create_provider = QComboBox()
        self.create_provider.addItems(["Cloudflare · Online", "ComfyUI · Local"])
        self.create_provider.currentIndexChanged.connect(self.update_create_provider)
        title.addWidget(self.create_provider)
        title.addWidget(button("Model setup", self.open_model_setup))
        form.addLayout(title)
        self.create_prompt = QPlainTextEdit()
        self.create_prompt.setPlaceholderText(
            "Describe the scene, lighting, and expression you want. Mention what to keep from your references.")
        self.create_prompt.setFixedHeight(94)
        form.addWidget(self.create_prompt)

        references = QHBoxLayout()
        self.create_reference_buttons = []
        self.create_clear_buttons = []
        for index, role in enumerate(("Composition reference", "Cast reference")):
            pick = button(role, partial(self.pick_create_reference, index), "", "image")
            clear = button("Clear", partial(self.set_create_reference, index, ""))
            clear.hide()
            references.addWidget(pick)
            references.addWidget(clear)
            self.create_reference_buttons.append(pick)
            self.create_clear_buttons.append(clear)
        references.addStretch()
        self.create_count = QComboBox()
        self.create_count.addItems(["1 draft", "3 concepts"])
        references.addWidget(self.create_count)
        self.generate_button = button("Generate", self.generate_images, "primary", "create")
        references.addWidget(self.generate_button)
        self.stop_generation = button("Stop after current", self.stop_after_current)
        self.stop_generation.hide()
        form.addLayout(references)
        layout.addWidget(composer)
        self.create_status = label("", "muted")
        self.create_status.setWordWrap(True)
        status_line = row(self.create_status, self.stop_generation)
        status_line.setStretch(0, 1)
        layout.addLayout(status_line)
        self.create_history = QComboBox()
        self.create_history.setAccessibleName("Draft history")
        self.create_history.currentIndexChanged.connect(self.open_draft_batch)
        self.reuse_prompt = button("Reuse prompt", self.use_saved_prompt)
        self.reuse_prompt.setEnabled(False)
        history = row(self.create_history, self.reuse_prompt)
        history.setStretch(0, 1)
        layout.addLayout(history)

        drafts = QHBoxLayout()
        self.draft_cards, self.draft_images, self.draft_destinations = [], [], []
        for index, letter in enumerate("ABC"):
            card = panel()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 12, 12, 12)
            card_layout.addWidget(label(f"Draft {letter}", "strong"))
            image = Picture(140)
            card_layout.addWidget(image, 1)
            destination = QComboBox()
            destination.addItems(list("ABC"))
            destination.setCurrentIndex(index)
            send = button("Send to Edit", partial(self.send_draft, index), "", "edit")
            card_layout.addLayout(row(destination, send))
            drafts.addWidget(card, 1)
            card.hide()
            self.draft_cards.append(card)
            self.draft_images.append(image)
            self.draft_destinations.append(destination)
        layout.addLayout(drafts, 1)
        self.update_create_provider()
        self.refresh_draft_history()
        if self.create_history.count() > 1:
            self.create_history.setCurrentIndex(1)
        return page

    def update_create_provider(self):
        local = self.create_provider.currentIndex() == 1
        for index, widget in enumerate(self.create_reference_buttons):
            widget.setVisible(local)
            self.create_clear_buttons[index].setVisible(local and bool(self.create_paths[index]))
        self.create_prompt.setPlaceholderText(
            "Describe the scene, lighting, and expression. Say what to keep from your references." if local
            else "Describe a movie scene, the main subject, and the mood.")
        self.create_status.setText("Start ComfyUI to generate with optional reference images." if local else
                                   "Online text-to-image. Connect Cloudflare Workers AI in Settings.")

    def open_model_setup(self):
        url = comfy.SETUP_URL if self.create_provider.currentIndex() else (
            "https://developers.cloudflare.com/workers-ai/get-started/rest-api/")
        QDesktopServices.openUrl(QUrl(url))

    def pick_create_reference(self, index):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a reference image", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)")
        if path:
            self.set_create_reference(index, path)

    def set_create_reference(self, index, path):
        self.create_paths[index] = path
        role = ("Composition reference", "Cast reference")[index]
        pick = self.create_reference_buttons[index]
        pick.setText(f"{role.split()[0]} · {Path(path).name[:20]}" if path else role)
        pick.setToolTip(path or role)
        self.create_clear_buttons[index].setVisible(bool(path) and self.create_provider.currentIndex() == 1)

    def generate_images(self):
        if not self.generate_button.isEnabled():
            return
        prompt = self.create_prompt.toPlainText().strip()
        if not prompt:
            self.create_status.setText("Enter a prompt to generate a thumbnail.")
            self.create_prompt.setFocus()
            return
        server = self.settings.value("create/server", comfy.DEFAULT_SERVER, type=str)
        online = self.create_provider.currentIndex() == 0
        account = self.settings.value("create/account", "", type=str)
        token = os.environ.get("CLOUDFLARE_API_TOKEN") or self.settings.value("create/token", "", type=str)
        references = tuple(zip(("composition reference", "cast reference"), self.create_paths))
        count = (1, 3)[self.create_count.currentIndex()]
        self.stop_batch.clear()
        self.generate_button.setEnabled(False)
        self.create_provider.setEnabled(False)
        self.create_history.setEnabled(False)
        self.reuse_prompt.setEnabled(False)
        self.stop_generation.setVisible(count > 1)
        self.stop_generation.setEnabled(True)
        self.create_status.setText(f"Generating draft 1 of {count}…")
        history_root = self.history_root

        def generate():
            outputs = []
            error = None
            save_error = None
            folder = None
            try:
                with requests.Session() as session:
                    session.trust_env = False
                    if online:
                        images = (services.cloud_image(account, token, f"{prompt} Cinematic YouTube movie thumbnail. {concept}")
                                  for concept in (comfy.CONCEPTS if count == 3 else ("",))
                                  if not self.create_stop.is_set())
                    else:
                        images = comfy.ComfyUI(server, self.create_stop, session).generate(prompt, references, count)
                    for data in images:
                        if data:
                            outputs.append((data, self.draft_preview(data)))
                            if save_error is None:
                                try:
                                    folder = services.save_draft(history_root, prompt, folder, len(outputs) - 1, data)
                                except (OSError, ValueError) as failure:
                                    save_error = f"Drafts are ready, but history could not be saved. {failure}"
                            self.draft_ready.emit(tuple(outputs), count)
                        if self.stop_batch.is_set():
                            break
            except Exception as failure:
                error = str(failure)
            return outputs, error or save_error, folder

        self.task(generate, self.generation_ready)

    def generation_ready(self, result, error):
        self.generate_button.setEnabled(True)
        self.create_provider.setEnabled(True)
        self.create_history.setEnabled(True)
        self.stop_generation.hide()
        generated, problem, folder = result if result else ([], error, None)
        if generated:
            self.refresh_draft_history(folder)
            self.display_drafts(generated)
        self.reuse_prompt.setEnabled(bool(self.create_history.currentData()))
        message = problem or f"{len(generated)} draft{'s' if len(generated) != 1 else ''} ready"
        self.create_status.setText(message)
        self.notice(message)

    def show_generation_progress(self, generated, count):
        self.display_drafts(generated)
        if self.stop_batch.is_set():
            self.create_status.setText("Finishing the current draft, then stopping…")
        elif len(generated) < count:
            self.create_status.setText(f"Generating draft {len(generated) + 1} of {count}…")
        else:
            self.create_status.setText("Saving drafts…")

    def stop_after_current(self):
        self.stop_batch.set()
        self.stop_generation.setEnabled(False)
        self.create_status.setText("Finishing the current draft, then stopping…")

    @staticmethod
    def draft_preview(data):
        image = ImageOps.fit(studio.open_image(data), (640, 360), method=Image.Resampling.LANCZOS)
        return Window.preview_image(image)

    def refresh_draft_history(self, folder=None):
        self.create_history.blockSignals(True)
        self.create_history.clear()
        self.create_history.addItem("Draft history")
        for path, prompt, count in services.batches(self.history_root):
            stamp = path.name[:17].replace("_", " ")
            self.create_history.addItem(f"{stamp[:13]}:{stamp[13:15]} · {prompt[:66]}", (str(path), count, prompt))
            if path == folder:
                self.create_history.setCurrentIndex(self.create_history.count() - 1)
        self.create_history.blockSignals(False)

    def open_draft_batch(self, index):
        item = self.create_history.itemData(index)
        self.reuse_prompt.setEnabled(bool(item))
        if not item:
            return
        folder, count, _ = item

        def load():
            data = [(Path(folder) / f"{number}.png").read_bytes() for number in range(count)]
            return [(image, self.draft_preview(image)) for image in data]

        def ready(result, error):
            if self.generate_button.isEnabled() and self.create_history.currentData() == item:
                if error:
                    self.create_status.setText(error)
                else:
                    self.display_drafts(result)
                    self.create_status.setText("Saved drafts")

        self.task(load, ready)

    def use_saved_prompt(self):
        item = self.create_history.currentData()
        if item:
            self.create_prompt.setPlainText(item[2])
            self.create_prompt.setFocus()

    def display_drafts(self, generated):
        self.create_outputs = [data for data, _ in generated]
        for index, card in enumerate(self.draft_cards):
            card.setVisible(index < len(generated))
            if index < len(generated):
                self.draft_images[index].set_data(generated[index][1])

    def send_draft(self, index):
        if index >= len(self.create_outputs):
            return
        slot = self.draft_destinations[index].currentIndex()
        if self.candidates[slot].source:
            answer = QMessageBox.question(self, "Replace candidate",
                                          f"Replace candidate {'ABC'[slot]} and its adjustments?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.install_source(slot, self.create_outputs[index], f"Generated draft {'ABC'[index]}")
        self.show_page(2)

    def start_search(self):
        query = self.query.text().strip()
        direct = video_id(query)
        if ("://" in query or query.lower().startswith(("youtu.be/", "youtube.com/", "www.youtube.com/"))) and not direct:
            self.notice("Enter a valid YouTube video URL.")
            return
        if not self.youtube.keys:
            self.notice("Add a YouTube Data API key in Settings to search.")
            return
        if not query and self.reference is None:
            self.notice("Enter a movie or actor name, paste a YouTube URL, or add a reference image.")
            return
        self.search_generation += 1
        self.search_pool.clear()
        self.image_pool.clear()
        self.tasks = {task for task in self.tasks if not task.is_search}
        for card in self.cards.values():
            self.results_grid.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards.clear()
        self.results.clear()
        self.rank.clear()
        self.next_token = None
        self.empty_pages = 0
        self.search_args = (query, 40, "" if self.genre.currentIndex() == 0 else self.genre.currentText())
        self.active_reference = self.reference
        self.sort_label.setText("By visual similarity" if self.active_reference else "By views")
        self.sort_label.hide()
        self.results_label.setText("Results")
        self.fetch_page(None)

    def fetch_page(self, token):
        self.searching = True
        self.more.hide()
        self.empty.setVisible(not self.results)
        self.empty.setText("Searching YouTube…")
        self.notice("Searching YouTube…")
        generation = self.search_generation
        client, args = self.youtube, self.search_args
        self.task(lambda: client.page(*args, token=token),
                  partial(self.page_ready, generation, token), self.search_pool)

    def page_ready(self, generation, token, result, error):
        if generation != self.search_generation:
            return
        self.searching = False
        if error:
            self.next_token = token
            self.more.setVisible(bool(token))
            self.empty.setText(error)
            self.notice(error)
            return
        videos, next_token = result
        self.next_token = next_token if next_token != token else None
        previous = len(self.results)
        for video in videos:
            if video.id in self.results:
                continue
            self.results[video.id] = video
            self.add_card(video, generation)
        self.arrange_cards()
        count = len(self.results)
        self.sort_label.setVisible(bool(count))
        self.results_label.setText(f"Results  ·  {count:,}")
        self.empty.setVisible(not count)
        self.empty.setText("No matching videos in the fetched results")
        self.more.setVisible(bool(self.next_token))
        self.notice(f"{count:,} fetched result{'s' if count != 1 else ''}")
        if count == previous and self.next_token and self.empty_pages < 2:
            self.empty_pages += 1
            QTimer.singleShot(0, self.load_more)

    def check_scroll(self, value):
        limit = self.result_scroll.verticalScrollBar().maximum()
        if limit > 0 and value >= limit - 120:
            self.load_more()

    def load_more(self):
        if not self.searching and self.next_token:
            self.fetch_page(self.next_token)

    def pick_reference(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose reference image", "", "Images (*.jpg *.jpeg *.png *.webp *.bmp)")
        if path:
            self.reference_button.setEnabled(False)
            self.task(lambda: signature(Path(path).read_bytes()), partial(self.reference_ready, path))

    def reference_ready(self, path, data, error):
        self.reference_button.setEnabled(True)
        if error:
            self.notice(error)
            return
        self.reference = data
        self.reference_button.setText(Path(path).name[:24])
        self.clear_reference.show()
        self.notice("Reference ready. Search to rank fetched thumbnails by visual similarity.")

    def remove_reference(self):
        self.reference = None
        self.reference_button.setText("Reference image")
        self.clear_reference.hide()
        self.notice("Reference cleared for the next search.")

    def add_card(self, video, generation):
        card = panel()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        image = Picture(136)
        self.decorate_picture(image)
        image.setFixedHeight(136)
        image.set_data(None, "Loading thumbnail…")
        layout.addWidget(image)
        title = label(video.title, "strong")
        title.setWordWrap(True)
        title.setMinimumHeight(35)
        title.setToolTip(video.title)
        layout.addWidget(title)
        caption = label(f"{video.channel}  ·  {video.date}", "muted")
        caption.setWordWrap(True)
        layout.addWidget(caption)
        layout.addWidget(label(f"{video.views:,} views", "muted"))
        layout.addStretch()
        actions = row(button("Save", partial(self.video_action, video, False), "", "save"),
                      button("Watch", lambda: QDesktopServices.openUrl(QUrl(video.url)), "", "watch"),
                      button("Edit", partial(self.video_action, video, True), "", "edit"))
        for index in range(actions.count()):
            self.decorate(actions.itemAt(index).widget())
        layout.addLayout(actions)
        self.cards[video.id] = card
        reference = self.active_reference

        def load():
            data = thumbnail(video, preview=True)
            return QImage.fromData(data), distance(reference, signature(data)) if reference else 0

        self.task(load, partial(self.card_ready, generation, video.id, image), self.image_pool)

    def card_ready(self, generation, key, image, result, error):
        if generation != self.search_generation:
            return
        if error:
            image.set_data(None, "Thumbnail unavailable")
            return
        pixmap, rank = result
        image.set_data(pixmap)
        if self.active_reference:
            self.rank[key] = rank
            if not self.rank_timer.isActive():
                self.rank_timer.start()

    def arrange_cards(self):
        columns = 3 if self.width() >= 1050 else 2
        self.columns = columns
        ordered = sorted(self.results.values(), key=lambda video: (self.rank.get(video.id, 2), -video.views))
        for card in self.cards.values():
            self.results_grid.removeWidget(card)
        for index, video in enumerate(ordered):
            self.results_grid.addWidget(self.cards[video.id], index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "results_grid") and self.results and self.columns != (3 if self.width() >= 1050 else 2):
            self.arrange_cards()

    def video_action(self, video, to_editor):
        slot = self.active
        if to_editor:
            dialog = QDialog(self, windowTitle="Choose candidate")
            form = QFormLayout(dialog)
            combo = QComboBox()
            combo.addItems(list("ABC"))
            combo.setCurrentIndex(slot)
            form.addRow("Send thumbnail to", combo)
            actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            actions.accepted.connect(dialog.accept)
            actions.rejected.connect(dialog.reject)
            form.addRow(actions)
            if not dialog.exec():
                return
            slot = combo.currentIndex()
        expected = self.candidates[slot]
        self.notice("Downloading best available source…")
        cached = self.cache.get(video.id)
        if cached:
            self.cache.move_to_end(video.id)
            self.video_ready(video, to_editor, slot, expected, cached, None)
        else:
            self.task(partial(thumbnail, video), partial(self.video_ready, video, to_editor, slot, expected))

    def video_ready(self, video, to_editor, slot, expected, data, error):
        if error:
            self.notice(error)
            return
        if video.id not in self.cache:
            self.cache[video.id] = data
            self.cache_bytes += len(data)
            while self.cache_bytes > 32 * 1024 * 1024:
                _, discarded = self.cache.popitem(last=False)
                self.cache_bytes -= len(discarded)
        if to_editor:
            if self.candidates[slot] is not expected:
                self.notice("Candidate changed during download. Send the image again to replace it.")
                return
            self.install_source(slot, data, video.title)
            self.show_page(2)
            return
        image = QImage.fromData(data)
        extension = ".png" if data.startswith(b"\x89PNG") else ".webp" if data.startswith(b"RIFF") else ".jpg"
        path, _ = QFileDialog.getSaveFileName(self, "Save original thumbnail", video.id + extension,
                                              f"Original thumbnail (*{extension})")
        if path:
            self.task(lambda: Path(path).write_bytes(data), lambda _, err: self.notice(
                err or f"Saved source · {image.width()} × {image.height()}"))

    def build_editor(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = row(label("Thumbnail studio", "heading"))
        heading.addStretch()
        self.movie = QLineEdit(placeholderText="Movie or project name")
        self.movie.setMinimumWidth(180)
        heading.addWidget(self.movie)
        self.export_button = button("Export A/B/C", self.export_candidates, "", "save")
        heading.addWidget(self.export_button)
        self.download_button = button("Download A", self.download_candidate, "primary", "save")
        self.download_button.setToolTip("Save the active candidate as a JPG.")
        heading.addWidget(self.download_button)
        layout.addLayout(heading)

        cards = QHBoxLayout()
        self.slot_cards, self.slot_images, self.slot_select = [], [], []
        for slot, letter in enumerate("ABC"):
            card = panel()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(9, 8, 9, 8)
            image = Picture(82)
            image.setMaximumHeight(111)
            image.set_data(None, "No source")
            card_layout.addWidget(image)
            select = button(f"Edit {letter}", partial(self.select_slot, slot))
            select.setCheckable(True)
            self.slot_select.append(select)
            card_layout.addLayout(row(select, button("Load image", partial(self.load_source, slot), "", "image")))
            cards.addWidget(card, 1)
            self.slot_cards.append(card)
            self.slot_images.append(image)
        layout.addLayout(cards)

        content = QHBoxLayout()
        left = panel()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 10, 12, 10)
        self.active_label = label("Candidate A", "strong")
        left_layout.addWidget(self.active_label)
        self.preview = Picture(220)
        self.preview.set_data(None, "Load an image to start editing")
        self.preview.selected.connect(self.remove_region)
        left_layout.addWidget(self.preview, 1)
        self.before = QCheckBox("Before adjustments")
        self.before.toggled.connect(self.before_toggled)
        self.small = QCheckBox("Small preview")
        self.small.toggled.connect(self.set_small)
        tools = row(self.before, self.small)
        tools.addStretch()
        left_layout.addLayout(tools)
        content.addWidget(left, 3)

        right = panel()
        right.setMinimumWidth(360)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 10, 10, 10)
        self.auto_button = button("Auto Adjust", self.auto_adjust, "primary", "create")
        self.auto_button.setMinimumWidth(108)
        self.remove_mode = QComboBox()
        self.remove_mode.addItems(["Remove", "Rectangle", "Brush"])
        self.remove_mode.setAccessibleName("Object or text remover")
        self.remove_mode.setMinimumWidth(112)
        self.remove_mode.currentIndexChanged.connect(self.toggle_remove)
        self.enhance_button = button("Enhance", self.enhance, "", "image")
        self.enhance_button.setToolTip("Upscale this candidate to 1920 × 1080 using the optional local AI tools.")
        right_layout.addLayout(row(self.auto_button, self.remove_mode, self.enhance_button))
        self.brush_width = QSpinBox()
        self.brush_width.setRange(1, 18)
        self.brush_width.setValue(4)
        self.brush_width.setPrefix("Brush ")
        self.brush_width.setSuffix("%")
        self.brush_width.valueChanged.connect(self.change_brush_width)
        self.brush_width.hide()
        self.preview.brush = 0.04
        right_layout.addWidget(self.brush_width)
        self.remove_actions = QWidget()
        selection_buttons = QHBoxLayout(self.remove_actions)
        selection_buttons.setContentsMargins(0, 0, 0, 0)
        self.apply_remove = button("Apply removal", self.apply_selection, "primary")
        self.undo_mark = button("Undo mark", self.undo_selection)
        self.clear_marks = button("Clear", self.clear_selection)
        for widget in (self.apply_remove, self.undo_mark, self.clear_marks):
            selection_buttons.addWidget(widget)
        self.remove_actions.hide()
        right_layout.addWidget(self.remove_actions)
        self.undo_button = button("Undo", partial(self.history, True))
        self.redo_button = button("Redo", partial(self.history, False))
        self.reset_button = button("Reset", self.reset)
        right_layout.addLayout(row(self.undo_button, self.redo_button, self.reset_button))
        advanced = button("Manual adjustments", lambda checked: scroll.setVisible(checked))
        advanced.setCheckable(True)
        right_layout.addWidget(advanced)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls = QWidget(objectName="scrollBody")
        self.form = QFormLayout(controls)
        self.form.setContentsMargins(10, 8, 10, 8)
        self.control_fields = {}
        for name, low, high in (("Crop horizontal", 0, 100), ("Crop vertical", 0, 100),
                                ("Crop zoom", 100, 220), *((name, -100, 100) for name in studio.ADJUSTMENTS),
                                ("JPEG quality", 70, 100)):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            value = label("", "muted")
            value.setFixedWidth(30)
            slider.valueChanged.connect(partial(self.slider_change, name))
            slider.sliderReleased.connect(self.commit)
            self.control_fields[name] = (slider, value)
            track = row(slider, value)
            track.setStretch(0, 1)
            self.form.addRow(name, track)
        self.overlay = QLineEdit(placeholderText="Optional title")
        self.overlay.setMaxLength(70)
        self.overlay.textChanged.connect(self.overlay_change)
        self.overlay.editingFinished.connect(self.commit)
        self.form.addRow("Text overlay", self.overlay)
        scroll.setWidget(controls)
        scroll.hide()
        right_layout.addWidget(scroll, 1)
        right_layout.addStretch()
        content.addWidget(right, 2)
        layout.addLayout(content, 1)
        return page

    def load_source(self, slot):
        path, _ = QFileDialog.getOpenFileName(self, f"Load candidate {'ABC'[slot]}", "",
                                              "Images (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)")
        if path:
            expected = self.candidates[slot]

            def load():
                data = Path(path).read_bytes()
                studio.open_image(data)
                return data

            self.notice("Loading image…")
            self.task(load, partial(self.local_ready, slot, expected, Path(path).name))

    def local_ready(self, slot, expected, filename, data, error):
        if error:
            self.notice(error)
        elif self.candidates[slot] is expected:
            self.install_source(slot, data, filename)
        else:
            self.notice("Candidate changed while loading. Choose the image again to replace it.")

    def install_source(self, slot, data, filename):
        self.commit()
        self.candidates[slot] = studio.Candidate(data, filename)
        self.slot_images[slot].set_data(None, "Rendering…")
        self.select_slot(slot, commit=False)
        self.notice(f"Candidate {'ABC'[slot]} loaded · {filename}")

    def select_slot(self, slot, commit=True):
        if commit:
            self.commit()
        self.active = slot
        self.clear_selection()
        self.before.setChecked(False)
        self.remove_mode.setCurrentIndex(0)
        self.preview.set_data(None, "Rendering…" if self.candidates[slot].source else "Load an image to start editing")
        self.sync_editor()

    def sync_editor(self):
        candidate = self.candidates[self.active]
        self.draft = candidate.edit
        self.active_label.setText(f"Candidate {'ABC'[self.active]}" + (f"  ·  {candidate.filename[:65]}" if candidate.source else ""))
        for index, card in enumerate(self.slot_cards):
            card.setObjectName("picked" if index == self.active else "surface")
            card.style().unpolish(card)
            card.style().polish(card)
            self.slot_select[index].setChecked(index == self.active)
        special = {"Crop horizontal": self.draft.crop, "Crop vertical": self.draft.vertical,
                   "Crop zoom": self.draft.zoom, "JPEG quality": self.draft.quality}
        for name, (widget, value) in self.control_fields.items():
            number = special.get(name, self.draft.values.get(name, 0))
            widget.blockSignals(True)
            widget.setValue(number)
            widget.blockSignals(False)
            locked = bool(self.draft.repaired) and name.startswith("Crop ")
            widget.setEnabled(bool(candidate.source) and not locked)
            widget.setToolTip("Undo or reset the AI edit to adjust the crop." if locked else "")
            value.setText(str(number))
        self.overlay.blockSignals(True)
        self.overlay.setText(self.draft.text)
        self.overlay.blockSignals(False)
        for widget in (self.overlay, self.before, self.small, self.auto_button, self.reset_button):
            widget.setEnabled(bool(candidate.source))
        self.update_actions()
        self.queue_preview()

    def update_actions(self):
        candidate = self.candidates[self.active]
        self.undo_button.setEnabled(bool(candidate.undo) or candidate.edit != self.draft)
        self.redo_button.setEnabled(bool(candidate.redo) and candidate.edit == self.draft)
        self.remove_mode.setEnabled(bool(candidate.source) and not self.offline_busy)
        self.enhance_button.setEnabled(bool(candidate.source) and not self.offline_busy and not self.draft.enhanced)
        self.enhance_button.setText("1080p ready" if self.draft.enhanced else "Enhance")
        self.download_button.setText(f"Download {'ABC'[self.active]}")
        self.download_button.setEnabled(bool(candidate.source) and not self.downloading and not self.offline_busy)
        for widget in (self.apply_remove, self.undo_mark, self.clear_marks):
            widget.setEnabled(bool(self.remove_selections) and not self.offline_busy)
        if not getattr(self, "exporting", False):
            self.export_button.setEnabled(all(candidate.source for candidate in self.candidates))

    def slider_change(self, name, value):
        self.control_fields[name][1].setText(str(value))
        attribute = {"Crop horizontal": "crop", "Crop vertical": "vertical", "Crop zoom": "zoom",
                     "JPEG quality": "quality"}.get(name)
        if attribute:
            if attribute != "quality" and self.remove_selections:
                self.clear_selection()
            self.draft = replace(self.draft, **{attribute: value})
        else:
            self.draft = replace(self.draft, values={**self.draft.values, name: value})
        self.update_actions()
        self.queue_preview()
        if not self.control_fields[name][0].isSliderDown():
            self.commit()

    def overlay_change(self, value):
        self.draft = replace(self.draft, text=value)
        self.update_actions()
        self.queue_preview()

    def commit(self):
        if hasattr(self, "draft"):
            self.candidates[self.active].change(self.draft)
            self.update_actions()

    def history(self, backwards):
        self.commit()
        self.clear_selection()
        self.candidates[self.active].step(backwards)
        self.sync_editor()

    def reset(self):
        self.commit()
        self.clear_selection()
        self.candidates[self.active].change(studio.Edit())
        self.sync_editor()

    def auto_adjust(self):
        self.commit()
        slot = self.active
        candidate = self.candidates[slot]
        self.notice("Calculating adjustments…")
        edit = candidate.edit
        def adjust():
            cropped = edit.repaired or studio.image_bytes(studio.crop_source(candidate.source, edit, (320, 180)))
            return studio.auto_adjust(cropped)
        self.task(adjust, partial(self.auto_ready, slot, candidate, edit))

    def auto_ready(self, slot, candidate, edit, values, error):
        if error:
            self.notice(error)
        else:
            self.commit()
            if self.candidates[slot] is not candidate or candidate.edit != edit:
                return
            candidate.change(replace(candidate.edit, values=values))
            if slot == self.active:
                self.sync_editor()
            else:
                self.queue_preview(slot)
            self.notice(f"Auto Adjust applied to candidate {'ABC'[slot]}")

    def before_toggled(self, enabled):
        if enabled:
            self.remove_mode.setCurrentIndex(0)
        self.queue_preview()

    def toggle_remove(self, mode):
        if mode != 0 and not offline.ready(self.model_root, "remove"):
            self.remove_mode.setCurrentIndex(0)
            slot = self.active
            candidate = self.candidates[slot]
            self.prepare_tool("remove", lambda: self.remove_mode.setCurrentIndex(mode)
                              if self.active == slot and self.candidates[slot] is candidate else None)
            return
        enabled = mode != 0
        self.preview.selectable = enabled
        self.preview.selection_mode = "brush" if mode == 2 else "box"
        self.brush_width.setVisible(mode == 2)
        self.remove_actions.setVisible(enabled)
        self.preview.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        if enabled:
            self.before.setChecked(False)
            self.notice("Mark the object or text, then select Apply removal.")
        else:
            self.clear_selection()

    def change_brush_width(self, value):
        self.preview.brush = value / 100

    def enhance(self):
        slot = self.active
        candidate = self.candidates[slot]
        self.prepare_tool("enhance", lambda: self.run_offline_edit(None)
                          if self.active == slot and self.candidates[slot] is candidate else None)

    def prepare_tool(self, tool, resume):
        if self.offline_busy:
            return
        if offline.ready(self.model_root, tool):
            resume()
            return
        model = offline.MODELS[tool]
        message = QMessageBox(QMessageBox.Icon.Information, f"Download {model.label}?",
                              f"Download {model.label} (about {model.megabytes} MB) for offline use?",
                              parent=self)
        if not (self.model_root / offline.RUNTIME / ".ready").is_file():
            message.setInformativeText("The first setup also downloads a shared AI engine for both tools.")
        accept = message.addButton("Download", QMessageBox.ButtonRole.AcceptRole)
        cancel = message.addButton(QMessageBox.StandardButton.Cancel)
        message.setDefaultButton(cancel)
        message.exec()
        if message.clickedButton() is not accept:
            return
        self.offline_busy = True
        self.remove_mode.setCurrentIndex(0)
        self.update_actions()
        self.notice(f"Setting up {model.label}…")

        def finished(_, error):
            self.offline_busy = False
            self.update_actions()
            self.notice(error or f"{model.label} is ready.")
            if not error:
                resume()

        self.task(lambda: offline.install(self.model_root, tool, self.offline_progress.emit, self.offline_stop),
                  finished)

    def remove_region(self, selection):
        self.remove_selections.append(selection)
        self.refresh_selection()

    def undo_selection(self):
        if self.remove_selections:
            self.remove_selections.pop()
            self.refresh_selection()

    def clear_selection(self):
        self.remove_selections.clear()
        self.refresh_selection()

    def refresh_selection(self):
        if self.remove_selections:
            size = (640, 360)
            mask = services.combined_mask(size, self.remove_selections)
            alpha = mask.point(lambda level: level * 120 // 255)
            overlay = Image.new("RGBA", size, (161, 120, 255))
            overlay.putalpha(alpha)
            self.preview.mask_preview = QImage(overlay.tobytes(), *size, size[0] * 4,
                                               QImage.Format.Format_RGBA8888).copy()
        else:
            self.preview.mask_preview = QImage()
        self.preview.update()
        self.update_actions()

    def apply_selection(self):
        if self.remove_selections:
            self.run_offline_edit(tuple(self.remove_selections))

    def run_offline_edit(self, selection):
        if self.offline_busy:
            return
        self.commit()
        slot = self.active
        candidate = self.candidates[slot]
        if not candidate.source:
            return
        edit = candidate.edit
        self.offline_busy = True
        if not selection:
            self.remove_mode.setCurrentIndex(0)
        self.preview.selectable = False
        self.update_actions()
        self.notice("Rebuilding the selected area with LaMa…" if selection else "Enhancing to 1920 × 1080…")

        def process():
            if edit.repaired:
                image = studio.open_image(edit.repaired)
            else:
                image = studio.crop_source(candidate.source, edit, studio.SIZE)
            return offline.process(self.model_root, image, selection, self.offline_progress.emit, self.offline_stop)

        self.task(process, partial(self.offline_ready, slot, candidate, edit, bool(selection)))

    def offline_ready(self, slot, candidate, edit, removal, data, error):
        self.offline_busy = False
        self.commit()
        self.preview.selectable = self.remove_mode.currentIndex() != 0
        if error:
            self.notice(error)
        elif self.candidates[slot] is candidate and (candidate.edit.crop, candidate.edit.vertical, candidate.edit.zoom,
               candidate.edit.repaired) == (edit.crop, edit.vertical, edit.zoom, edit.repaired):
            candidate.change(replace(candidate.edit, repaired=data, enhanced=edit.enhanced or not removal))
            if slot == self.active:
                if removal:
                    self.clear_selection()
                self.sync_editor()
            else:
                self.queue_preview(slot)
            self.notice("Selection rebuilt." if removal else "Enhanced to 1920 × 1080.")
        else:
            self.notice("The candidate changed while the AI job was running. Run the tool again.")

    def download_candidate(self):
        self.commit()
        candidate = self.candidates[self.active]
        if self.downloading or not candidate.source:
            return
        letter = "ABC"[self.active]
        folder = self.settings.value("exports", "", type=str)
        suggested = str(Path(folder) / f"Candidate {letter}.jpg")
        dialog = QFileDialog(self, "Download edited thumbnail", suggested, "JPEG image (*.jpg *.jpeg)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setDefaultSuffix("jpg")
        if not dialog.exec():
            return
        path = Path(dialog.selectedFiles()[0])
        snapshot = studio.Candidate(candidate.source, candidate.filename, candidate.edit)
        self.settings.setValue("exports", str(path.parent))
        self.downloading = True
        self.update_actions()
        self.notice(f"Saving candidate {letter}…")

        def finished(size, error):
            self.downloading = False
            self.update_actions()
            self.notice(error or f"Saved {path.name} · {size[0]} × {size[1]}")

        self.task(lambda: studio.download(snapshot, path), finished)

    def set_small(self, enabled):
        self.preview.setMaximumSize(240, 135) if enabled else self.preview.setMaximumSize(16777215, 16777215)
        self.preview.setMinimumHeight(100 if enabled else 220)

    def queue_preview(self, slot=None):
        slot = self.active if slot is None else slot
        self.preview_revision[slot] += 1
        if self.candidates[slot].source:
            self.preview_dirty.add(slot)
            if not self.preview_busy:
                self.preview_timer.start()

    def update_previews(self):
        if not self.preview_dirty:
            return
        active = self.active
        slot = active if active in self.preview_dirty else min(self.preview_dirty)
        self.preview_dirty.remove(slot)
        candidate = self.candidates[slot]
        edit = self.draft if slot == active else candidate.edit
        before = slot == active and self.before.isChecked()
        revision = self.preview_revision[slot]
        self.preview_busy = True

        def render():
            picture = studio.render(candidate.source, edit, (640, 360))
            edited = self.preview_image(picture)
            original = self.preview_image(studio.render(candidate.source, edit, (640, 360),
                                                        original=True)) if before else edited
            return edited, original

        self.task(render, partial(self.preview_ready, slot, revision))

    @staticmethod
    def preview_image(image):
        return QImage(image.tobytes(), image.width, image.height, image.width * 3,
                      QImage.Format.Format_RGB888).copy()

    def preview_ready(self, slot, revision, pictures, error):
        self.preview_busy = False
        if revision == self.preview_revision[slot]:
            if error:
                self.notice(error)
            else:
                edited, current = pictures
                self.slot_images[slot].set_data(edited)
                if slot == self.active:
                    self.preview.set_data(current)
        if self.preview_dirty:
            self.preview_timer.start(0)

    def export_candidates(self):
        self.commit()
        folder = QFileDialog.getExistingDirectory(self, "Choose export folder", self.settings.value("exports", ""))
        if folder:
            self.settings.setValue("exports", folder)
            snapshot = [studio.Candidate(candidate.source, candidate.filename, candidate.edit) for candidate in self.candidates]
            movie = self.movie.text()
            self.exporting = True
            self.export_button.setEnabled(False)
            self.notice("Exporting three JPGs…")
            self.task(lambda: studio.export(snapshot, folder, movie), self.export_ready)

    def export_ready(self, path, error):
        self.exporting = False
        self.update_actions()
        if error:
            self.notice(error)
        else:
            self.notice(f"Exported A, B and C · {path}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_settings(self):
        dialog = QDialog(self, windowTitle="Settings")
        dialog.setMinimumWidth(425)
        form = QFormLayout(dialog)
        keys = []
        for index in (1, 2):
            field = QLineEdit(self.settings.value(f"youtube/key{index}", ""))
            field.setEchoMode(QLineEdit.EchoMode.Password)
            field.setPlaceholderText("Uses the environment or build default if blank")
            form.addRow(f"YouTube API key {index}", field)
            keys.append(field)
        appearance = QComboBox()
        appearance.addItems(["System", "Light", "Dark"])
        appearance.setCurrentIndex((2 if self.dark else 1) if self.settings.contains("dark") else 0)
        form.addRow("Appearance", appearance)
        server = QLineEdit(self.settings.value("create/server", comfy.DEFAULT_SERVER, type=str))
        server.setPlaceholderText(comfy.DEFAULT_SERVER)
        form.addRow("ComfyUI server", server)
        account = QLineEdit(self.settings.value("create/account", "", type=str))
        token = QLineEdit(self.settings.value("create/token", "", type=str))
        token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Cloudflare account ID", account)
        form.addRow("Workers AI token", token)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        def save():
            try:
                comfy.server_url(server.text() or comfy.DEFAULT_SERVER)
            except ValueError as error:
                QMessageBox.warning(dialog, "ComfyUI server", str(error))
            else:
                dialog.accept()

        actions.accepted.connect(save)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if dialog.exec():
            self.settings.setValue("create/server", comfy.server_url(server.text() or comfy.DEFAULT_SERVER))
            self.settings.setValue("create/account", account.text().strip())
            self.settings.setValue("create/token", token.text().strip())
            for index, field in enumerate(keys, 1):
                self.settings.setValue(f"youtube/key{index}", field.text().strip())
            new = self.make_youtube()
            if new.keys != self.youtube.keys:
                self.youtube = new
            if appearance.currentIndex():
                self.dark = appearance.currentIndex() == 2
                self.settings.setValue("dark", self.dark)
            else:
                self.settings.remove("dark")
                self.dark = QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
            self.theme.animate(self.dark)
            self.apply_theme()
            self.notice("Settings saved")

    def check_updates(self):
        self.notice("Checking for updates…")

        def check():
            url = REPOSITORY.replace("github.com", "api.github.com/repos") + "/releases/latest"
            response = requests.get(url, timeout=(4, 8))
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json().get("tag_name", "").lstrip("v")

        self.task(check, self.updates_ready)

    def updates_ready(self, version, error):
        if error:
            text = "The update check could not reach GitHub."
        elif not version:
            text = "GitHub did not return a published release."
        else:
            def parts(value):
                import re
                numbers = tuple(map(int, re.findall(r"\d+", value.split("-")[0])[:3]))
                return (numbers + (0, 0, 0))[:3]
            text = f"Thumb Finder {version} is available." if parts(version) > parts(VERSION) else f"You are using Thumb Finder v{VERSION}."
        self.notice(text)
        message = QMessageBox(QMessageBox.Icon.Information, "Check for updates", text, parent=self)
        releases = message.addButton("Open GitHub Releases", QMessageBox.ButtonRole.ActionRole)
        message.addButton(QMessageBox.StandardButton.Close)
        message.exec()
        if message.clickedButton() is releases:
            QDesktopServices.openUrl(QUrl(REPOSITORY + "/releases"))

    def closeEvent(self, event):
        self.create_stop.set()
        self.offline_stop.set()
        self.search_generation += 1
        self.preview_timer.stop()
        for pool in (self.image_pool, self.search_pool, self.pool):
            pool.clear()
        super().closeEvent(event)
