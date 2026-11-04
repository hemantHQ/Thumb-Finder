import os, sys, json, requests
from pathlib import Path
from datetime import datetime
from urllib.parse import quote
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QUrl, QSize, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices, QFont, QIcon, QPainter, QColor
from PySide6.QtWidgets import QSplashScreen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QSpinBox, QFrame, QScrollArea,
    QGridLayout, QFileDialog, QMessageBox, QProgressBar, QDialog,
    QFormLayout, QDialogButtonBox, QCheckBox, QSlider
)

try:
    import cv2
    import numpy as np
    CV_AVAILABLE = True
except Exception:
    cv2 = None
    np = None
    CV_AVAILABLE = False

try:
    from .version import __version__
except ImportError:
    try:
        from thumb_finder.version import __version__
    except ImportError:
        from version import __version__

APP_NAME = "Thumb Finder"
APP_VERSION = __version__

def load_youtube_api_key():
    """Load CI-injected key, or environment variable for local development."""
    try:
        from .api_config import YOUTUBE_API_KEY
    except ImportError:
        try:
            from thumb_finder.api_config import YOUTUBE_API_KEY
        except ImportError:
            try:
                from api_config import YOUTUBE_API_KEY
            except ImportError:
                YOUTUBE_API_KEY = ""
    return (YOUTUBE_API_KEY or os.environ.get("THUMB_FINDER_YOUTUBE_API_KEY", "")).strip()

CONFIG_PATH = Path.home() / ".thumb_finder" / "config.json"
DOWNLOAD_ROOT = Path.home() / "Pictures" / "Thumb Finder"
BATCH_SIZE = 20  # Results are loaded automatically as the gallery is scrolled.

DARK = """
QWidget { background:#10111b; color:#f4f3fb; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#10111b; }
QFrame#Sidebar { background:#171827; border:1px solid #292a40; border-radius:20px; }
QFrame#Panel { background:#171827; border:1px solid #292a40; border-radius:18px; }
QFrame#Card { background:#191b2b; border:1px solid #2c2e45; border-radius:16px; }
QFrame#Card:hover { border:1px solid #7569ef; background:#1c1e30; }
QLabel#Muted { color:#9a9bb4; }
QLabel#Eyebrow { color:#9b91ff; font-size:8pt; font-weight:800; letter-spacing:1px; }
QLabel#PageTitle { font-size:23pt; font-weight:800; color:#faf9ff; }
QLabel#SectionTitle { font-size:12pt; font-weight:750; }
QLabel#Metric { font-size:17pt; font-weight:800; color:#fff; }
QLineEdit, QComboBox, QSpinBox { background:#202238; border:1px solid #343650; border-radius:11px; padding:12px 13px; color:#f7f6ff; selection-background-color:#6657e8; min-height:20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid #8b80ff; background:#242640; }
QComboBox::drop-down { border:0; width:28px; }
QComboBox QAbstractItemView { background:#202238; color:#f7f6ff; border:1px solid #414363; selection-background-color:#6657e8; padding:6px; }
QPushButton { background:#6657e8; color:white; border:0; border-radius:11px; padding:11px 15px; font-weight:700; }
QPushButton:hover { background:#796cf2; }
QPushButton:pressed { background:#5143c5; }
QPushButton:disabled { background:#39384f; color:#77788f; }
QPushButton#Secondary { background:#282a40; border:1px solid #393b56; color:#e8e6fa; }
QPushButton#Secondary:hover { background:#333550; border-color:#5d5a8b; }
QPushButton#Ghost { background:transparent; border:1px solid #393b56; color:#d8d6ec; }
QPushButton#Ghost:hover { background:#24263a; }
QPushButton#SmallAction { padding:8px 10px; font-size:9pt; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:transparent; width:9px; margin:4px 1px; }
QScrollBar::handle:vertical { background:#41435e; border-radius:4px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:#7067c6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QProgressBar { border:0; border-radius:4px; background:#2b2d43; height:7px; text-align:center; }
QProgressBar::chunk { background:#8b80ff; border-radius:4px; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; }
QDialog { background:#171827; }
QDialogButtonBox QPushButton { min-width:95px; }
"""
LIGHT = """
QWidget { background:#f5f6fc; color:#22243a; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#f5f6fc; }
QFrame#Sidebar { background:#ffffff; border:1px solid #e4e6f1; border-radius:20px; }
QFrame#Panel { background:#ffffff; border:1px solid #e4e6f1; border-radius:18px; }
QFrame#Card { background:#ffffff; border:1px solid #e5e7f0; border-radius:16px; }
QFrame#Card:hover { border:1px solid #938af0; background:#fdfdff; }
QLabel#Muted { color:#777b92; }
QLabel#Eyebrow { color:#6657d9; font-size:8pt; font-weight:800; letter-spacing:1px; }
QLabel#PageTitle { font-size:23pt; font-weight:800; color:#202238; }
QLabel#SectionTitle { font-size:12pt; font-weight:750; }
QLabel#Metric { font-size:17pt; font-weight:800; color:#22243a; }
QLineEdit, QComboBox, QSpinBox { background:#fafaff; border:1px solid #dfe1ed; border-radius:11px; padding:12px 13px; color:#252740; min-height:20px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border:1px solid #8175eb; background:#fff; }
QComboBox::drop-down { border:0; width:28px; }
QComboBox QAbstractItemView { background:white; color:#252740; border:1px solid #dfe1ed; selection-background-color:#e9e6ff; padding:6px; }
QPushButton { background:#6657e8; color:white; border:0; border-radius:11px; padding:11px 15px; font-weight:700; }
QPushButton:hover { background:#796cf2; }
QPushButton:pressed { background:#5143c5; }
QPushButton:disabled { background:#d4d1ed; color:#fff; }
QPushButton#Secondary { background:#f0effa; border:1px solid #e2e0f2; color:#393653; }
QPushButton#Secondary:hover { background:#e8e6f8; border-color:#c9c4ed; }
QPushButton#Ghost { background:transparent; border:1px solid #dedfed; color:#53566d; }
QPushButton#Ghost:hover { background:#f0f0f8; }
QPushButton#SmallAction { padding:8px 10px; font-size:9pt; }
QScrollArea { border:0; background:transparent; }
QScrollBar:vertical { background:transparent; width:9px; margin:4px 1px; }
QScrollBar::handle:vertical { background:#d1d3e2; border-radius:4px; min-height:28px; }
QScrollBar::handle:vertical:hover { background:#aaa4e5; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QProgressBar { border:0; border-radius:4px; background:#e6e7f0; height:7px; text-align:center; }
QProgressBar::chunk { background:#6657e8; border-radius:4px; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:17px; height:17px; }
QDialog { background:#fff; }
QDialogButtonBox QPushButton { min-width:95px; }
"""

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(data):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

class WorkerSignals(QObject):
    finished = Signal(object, object)
    progress = Signal(str)

class SearchWorker(QRunnable):
    """Fetch popular long-form videos; image mode compares their thumbnails locally."""
    def __init__(self, api_key, query, page_token="", batch_size=BATCH_SIZE,
                 min_minutes=30, reference_image=""):
        super().__init__()
        self.api_key, self.query, self.page_token = api_key, query, page_token
        self.batch_size = batch_size
        self.min_seconds = int(min_minutes) * 60
        self.reference_image = reference_image
        self.image_mode = bool(reference_image)

    @staticmethod
    def duration_seconds(value):
        import re
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
        return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 +
                int(m.group(3) or 0)) if m else 0

    @staticmethod
    def _visual_signature(image_bytes):
        if not CV_AVAILABLE or not image_bytes:
            return None
        data = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            return None
        image = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        tiny = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
        dhash = (tiny[:, 1:] > tiny[:, :-1]).flatten()
        return hist, dhash

    @staticmethod
    def _similarity(a, b):
        if a is None or b is None:
            return 0.0
        hist_score = max(0.0, float(cv2.compareHist(a[0], b[0], cv2.HISTCMP_CORREL)))
        hash_score = 1.0 - float(np.count_nonzero(a[1] != b[1])) / 64.0
        return max(0.0, min(1.0, 0.55 * hist_score + 0.45 * hash_score))

    def run(self):
        try:
            reference_signature = None
            if self.image_mode:
                if not CV_AVAILABLE:
                    raise RuntimeError("Image similarity needs OpenCV and NumPy. Reinstall requirements.txt.")
                reference_bytes = Path(self.reference_image).read_bytes()
                reference_signature = self._visual_signature(reference_bytes)
                if reference_signature is None:
                    raise RuntimeError("The selected reference image could not be read.")

            token = self.page_token
            results, visited = [], set()
            next_token = token
            pages_checked = 0
            # Image mode searches a larger candidate pool; matching happens on this PC.
            max_pages = 5 if self.image_mode else 100
            while len(results) < self.batch_size and pages_checked < max_pages:
                self.signals.progress.emit(
                    f"Finding popular videos… {len(results)}/{self.batch_size}")
                params = {"part": "snippet", "type": "video", "maxResults": 50,
                          "order": "viewCount", "key": self.api_key}
                if self.query:
                    params["q"] = self.query
                if token:
                    params["pageToken"] = token
                r = requests.get("https://www.googleapis.com/youtube/v3/search",
                                 params=params, timeout=25)
                r.raise_for_status()
                payload = r.json()
                raw = payload.get("items", [])
                ids = [x.get("id", {}).get("videoId") for x in raw]
                ids = [x for x in ids if x and x not in visited]
                visited.update(ids)
                details = {}
                if ids:
                    self.signals.progress.emit("Checking video duration and popularity…")
                    vr = requests.get("https://www.googleapis.com/youtube/v3/videos",
                        params={"part": "contentDetails,statistics", "id": ",".join(ids),
                                "key": self.api_key}, timeout=25)
                    vr.raise_for_status()
                    details = {x["id"]: x for x in vr.json().get("items", [])}
                for item in raw:
                    vid = item.get("id", {}).get("videoId")
                    if not vid or vid not in details:
                        continue
                    detail = details[vid]
                    seconds = self.duration_seconds(
                        detail.get("contentDetails", {}).get("duration", ""))
                    if seconds < self.min_seconds:
                        continue
                    sn = item.get("snippet", {})
                    thumbs = sn.get("thumbnails", {})
                    quality_order = ("maxres", "standard", "high", "medium", "default")
                    best_quality = next((k for k in quality_order
                        if k in thumbs and thumbs[k].get("url")), "")
                    best_thumb = thumbs.get(best_quality, {})
                    best = best_thumb.get("url", "")
                    similarity = None
                    if self.image_mode:
                        try:
                            tr = requests.get(best, timeout=12)
                            tr.raise_for_status()
                            candidate_signature = self._visual_signature(tr.content)
                            similarity = self._similarity(reference_signature, candidate_signature)
                        except Exception:
                            continue
                        # Only keep visually related thumbnails; this is not face recognition.
                        if similarity < 0.38:
                            continue
                    stats = detail.get("statistics", {})
                    result = {
                        "id": vid, "title": sn.get("title", "Untitled"),
                        "channel": sn.get("channelTitle", ""),
                        "published": sn.get("publishedAt", "")[:10],
                        "views": int(stats.get("viewCount", 0)),
                        "thumbnail": best, "thumbnail_quality": best_quality,
                        "thumbnail_width": best_thumb.get("width", 0),
                        "thumbnail_height": best_thumb.get("height", 0),
                        "duration": seconds,
                        "video_url": "https://www.youtube.com/watch?v=" + vid
                    }
                    if similarity is not None:
                        result["similarity"] = similarity
                    results.append(result)
                next_token = payload.get("nextPageToken", "")
                pages_checked += 1
                if not next_token or not raw:
                    break
                if pages_checked >= max_pages:
                    # Bound the local image-search candidate pool to avoid excessive API quota use.
                    next_token = ""
                    break
                token = next_token
            # In every mode, popular videos are shown first.
            results.sort(key=lambda x: x["views"], reverse=True)
            self.signals.finished.emit({"items": results, "next": next_token}, None)
        except Exception as e:
            self.signals.finished.emit(None, str(e))

class ImageSignals(QObject):
    done = Signal(bytes)

class DownloadSignals(QObject):
    done = Signal(str, str)

class DownloadWorker(QRunnable):
    def __init__(self, items, folder):
        super().__init__(); self.items=items; self.folder=folder; self.signals=DownloadSignals()
    def run(self):
        try:
            self.folder.mkdir(parents=True,exist_ok=True); saved=0
            for item in self.items:
                if not item.get("thumbnail"): continue
                r=requests.get(item["thumbnail"],timeout=20); r.raise_for_status()
                name="".join(c for c in item["title"] if c.isalnum() or c in " -_").strip().replace(" ","_")[:75] or item["id"]
                content_type = r.headers.get("Content-Type", "").split(";")[0].lower()
                ext = { "image/jpeg": ".jpg", "image/png": ".png",
                        "image/webp": ".webp", "image/gif": ".gif" }.get(content_type, ".jpg")
                # Preserve the original highest-available thumbnail bytes without resizing or recompressing.
                (self.folder/f"{name}_{item['id']}{ext}").write_bytes(r.content)
                saved += 1
            self.signals.done.emit(f"Downloaded {saved} thumbnail(s).", "")
        except Exception as e: self.signals.done.emit("Download failed.",str(e))

class ImageWorker(QRunnable):
    def __init__(self, url):
        super().__init__(); self.url=url; self.signals=ImageSignals()
    def run(self):
        try:
            r=requests.get(self.url,timeout=12); r.raise_for_status(); self.signals.done.emit(r.content)
        except Exception: self.signals.done.emit(b"")

class SettingsDialog(QDialog):
    def __init__(self, parent, download_dir):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(14)
        self.download_path = QLineEdit(str(download_dir))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self.browse_folder)
        path_row = QHBoxLayout()
        path_row.addWidget(self.download_path, 1)
        path_row.addWidget(browse)
        form.addRow("Download location", path_row)
        layout.addLayout(form)
        note = QLabel("YouTube API access is configured by the Thumb Finder publisher. No API key is required from users.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.download_path.text().strip() or str(DOWNLOAD_ROOT))
        if folder:
            self.download_path.setText(folder)


class ThumbCard(QFrame):
    def __init__(self, item, parent):
        super().__init__()
        self.setObjectName("Card")
        self.item = item
        self.parent_window = parent
        self.setMinimumWidth(230)
        self.setMaximumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.image = QLabel("Loading preview…")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumHeight(138)
        self.image.setMaximumHeight(190)
        self.image.setStyleSheet("background:rgba(120,120,140,0.12); border-radius:11px; color:#999;")
        layout.addWidget(self.image)

        title = QLabel(item["title"])
        title.setWordWrap(True)
        title.setMinimumHeight(40)
        title.setMaximumHeight(48)
        title.setStyleSheet("font-size:10pt;font-weight:700;background:transparent;border:0;")
        title.setToolTip(item["title"])
        layout.addWidget(title)

        views = QLabel(f"◉  {item['views']:,} views")
        views.setStyleSheet("font-weight:700;color:#8b80ff;background:transparent;border:0;")
        layout.addWidget(views)
        if item.get("similarity") is not None:
            match = QLabel(f"▧  Visual match · {item['similarity'] * 100:.0f}%")
            match.setStyleSheet("font-weight:700;color:#9b91ff;background:transparent;border:0;")
            layout.addWidget(match)
        meta = QLabel(f"{item.get('published','')}   ·   {item.get('duration',0)//60} min+\n{item.get('channel','')}")
        meta.setObjectName("Muted")
        meta.setWordWrap(True)
        meta.setStyleSheet("font-size:8.5pt;background:transparent;border:0;")
        layout.addWidget(meta)

        row = QHBoxLayout()
        row.setSpacing(7)
        dl = QPushButton("↓  Save")
        dl.setObjectName("SmallAction")
        dl.clicked.connect(lambda: parent.download_item(item))
        openb = QPushButton("▶  Watch")
        openb.setObjectName("Secondary")
        openb.setProperty("class", "secondary")
        openb.setStyleSheet("padding:8px 10px;font-size:9pt;")
        openb.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(item["video_url"])))
        row.addWidget(dl, 1); row.addWidget(openb, 1)
        layout.addLayout(row)

        if item.get("thumbnail"):
            worker = ImageWorker(item["thumbnail"])
            worker.signals.done.connect(self.set_image)
            parent.image_workers.append(worker)
            worker.signals.done.connect(lambda _data, w=worker: parent.image_workers.remove(w) if w in parent.image_workers else None)
            parent.pool.start(worker)

    def set_image(self, data):
        if not data:
            self.image.setText("Preview unavailable")
            return
        pix = QPixmap()
        pix.loadFromData(data)
        if not pix.isNull():
            self.image.setPixmap(pix.scaled(420, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.image.setText("Preview unavailable")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.api_key = load_youtube_api_key()
        self.download_dir = Path(self.config.get(
            "download_dir", str(DOWNLOAD_ROOT))).expanduser()
        self.dark = self.config.get("dark", True)
        self.next_token = ""
        self.last_query = ""
        self.loading_more = False
        self.auto_load_enabled = True
        self.has_more_pages = False
        self.min_duration_minutes = int(self.config.get("min_duration_minutes", 30))
        self.search_folder_name = ""
        self.search_image_path = ""
        self.seen_ids = set()
        self.pool = QThreadPool.globalInstance()
        self.image_workers = []
        self.download_workers = []
        self._visible_cards = []
        self.setWindowTitle("Thumb Finder")
        icon_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app_icon.svg"
        if icon_path.exists(): self.setWindowIcon(QIcon(str(icon_path)))
        self.setMinimumSize(1050,700)
        self.resize(1250,820)
        self.build_ui()
        self.apply_theme()

    def run_first_launch_setup(self):
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.config.setdefault("setup_complete", True)
        self.config.setdefault("download_dir", str(self.download_dir))
        save_config(self.config)
        if not self.api_key:
            QMessageBox.critical(
                self, "Configuration unavailable",
                "This build has no YouTube API configuration. Please download an official release."
            )
            return False
        return True

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(26, 22, 26, 20)
        root.setSpacing(18)

        # Header / brand bar
        header = QHBoxLayout()
        header.setSpacing(13)
        logo = QLabel("✦")
        logo.setFixedSize(48, 48)
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background:#6657e8;color:white;border-radius:15px;font-size:24pt;font-weight:800;")
        header.addWidget(logo)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        name = QLabel("Thumb Finder")
        name.setStyleSheet("font-size:19pt;font-weight:850;letter-spacing:-0.4px;background:transparent;")
        tagline = QLabel("Discover. Explore. Get Inspired.")
        tagline.setObjectName("Muted")
        tagline.setStyleSheet("font-size:9pt;background:transparent;")
        brand.addWidget(name)
        brand.addWidget(tagline)
        header.addLayout(brand)
        header.addStretch()
        self.theme_btn = QPushButton("☀  Light mode" if self.dark else "☾  Dark mode")
        self.theme_btn.setObjectName("Ghost")
        self.theme_btn.clicked.connect(self.toggle_theme)
        settings = QPushButton("⚙  Settings")
        settings.setObjectName("Secondary")
        settings.clicked.connect(self.open_settings)
        header.addWidget(self.theme_btn)
        header.addWidget(settings)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)

        # Left search workspace
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(315)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 20, 20, 20)
        side.setSpacing(13)

        eyebrow = QLabel("SEARCH WORKSPACE")
        eyebrow.setObjectName("Eyebrow")
        side.addWidget(eyebrow)
        search_title = QLabel("Find your next\ninspiration.")
        search_title.setStyleSheet("font-size:19pt;font-weight:850;line-height:1.2;background:transparent;")
        side.addWidget(search_title)
        intro = QLabel("Explore long-form YouTube videos and save their original thumbnails.")
        intro.setObjectName("Muted")
        intro.setWordWrap(True)
        intro.setStyleSheet("font-size:9pt;background:transparent;")
        side.addWidget(intro)
        side.addSpacing(5)

        mode_label = QLabel("SEARCH TYPE")
        mode_label.setObjectName("Eyebrow")
        side.addWidget(mode_label)
        self.mode = QComboBox()
        self.mode.addItems(["Actor name", "Topic search", "Similar thumbnail image"])
        self.mode.setToolTip("Image mode compares the selected thumbnail with popular YouTube thumbnails using local visual similarity. It does not identify people.")
        self.mode.currentIndexChanged.connect(self.update_placeholders)
        side.addWidget(self.mode)

        self.actor = QLineEdit()
        self.actor.setPlaceholderText("e.g. Shah Rukh Khan — popular videos featuring this actor")
        side.addWidget(self.actor)
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("e.g. gaming, travel, tech reviews — popular videos first")
        side.addWidget(self.topic)

        self.image_row = QHBoxLayout()
        self.image_preview = QLabel("Choose a thumbnail to find visually similar thumbnails")
        self.image_preview.setObjectName("Muted")
        self.image_preview.setMinimumHeight(44)
        self.image_preview.setWordWrap(True)
        self.image_btn = QPushButton("＋ Choose image")
        self.image_btn.setObjectName("Secondary")
        self.image_btn.clicked.connect(self.choose_reference_image)
        self.image_row.addWidget(self.image_preview, 1)
        self.image_row.addWidget(self.image_btn)
        side.addLayout(self.image_row)
        self.actor_image_path = ""

        side.addSpacing(4)
        duration_label = QLabel("MINIMUM VIDEO LENGTH")
        duration_label.setObjectName("Eyebrow")
        side.addWidget(duration_label)
        self.duration_choice = QComboBox()
        self.duration_choice.addItems(["30 minutes+", "40 minutes+", "50 minutes+", "Custom…"])
        preset = {30: 0, 40: 1, 50: 2}.get(self.min_duration_minutes, 3)
        self.duration_choice.setCurrentIndex(preset)
        side.addWidget(self.duration_choice)
        self.custom_minutes = QSpinBox()
        self.custom_minutes.setRange(30, 360)
        self.custom_minutes.setSingleStep(5)
        self.custom_minutes.setSuffix(" minutes+")
        self.custom_minutes.setValue(max(30, min(360, self.min_duration_minutes)))
        self.custom_minutes.setVisible(preset == 3)
        self.custom_minutes.setToolTip("Set any minimum duration from 30 to 360 minutes.")
        side.addWidget(self.custom_minutes)
        self.duration_choice.currentIndexChanged.connect(
            lambda i: self.custom_minutes.setVisible(i == 3))

        self.search_btn = QPushButton("⌕   Find thumbnails")
        self.search_btn.setMinimumHeight(48)
        self.search_btn.clicked.connect(self.start_search)
        side.addWidget(self.search_btn)
        side.addStretch(1)

        tip = QFrame()
        tip.setStyleSheet("background:rgba(102,87,232,0.12);border:1px solid rgba(130,117,255,0.25);border-radius:12px;")
        tip_l = QVBoxLayout(tip)
        tip_l.setContentsMargins(12, 10, 12, 10)
        tip_l.setSpacing(4)
        tip_head = QLabel("✦  Smart filtering")
        tip_head.setStyleSheet("font-weight:750;color:#9b91ff;background:transparent;border:0;")
        tip_body = QLabel("Only videos meeting your minimum length are shown. Popular results load automatically as you scroll.")
        tip_body.setWordWrap(True)
        tip_body.setStyleSheet("font-size:8.5pt;color:#a7a5bf;background:transparent;border:0;")
        tip_l.addWidget(tip_head)
        tip_l.addWidget(tip_body)
        side.addWidget(tip)
        body.addWidget(sidebar)

        # Right results workspace
        content = QVBoxLayout()
        content.setSpacing(13)
        content_header = QHBoxLayout()
        heading_col = QVBoxLayout()
        heading_col.setSpacing(2)
        results_title = QLabel("Your gallery")
        results_title.setObjectName("PageTitle")
        self.result_label = QLabel("Your saved-worthy thumbnail discoveries will appear here.")
        self.result_label.setObjectName("Muted")
        self.result_label.setStyleSheet("font-size:9pt;background:transparent;")
        heading_col.addWidget(results_title)
        heading_col.addWidget(self.result_label)
        content_header.addLayout(heading_col)
        content_header.addStretch()
        self.download_all_btn = QPushButton("↓  Download all shown")
        self.download_all_btn.setObjectName("Secondary")
        self.download_all_btn.setEnabled(False)
        self.download_all_btn.clicked.connect(self.download_all)
        content_header.addWidget(self.download_all_btn)
        content.addLayout(content_header)

        status_panel = QFrame()
        status_panel.setObjectName("Panel")
        status_l = QHBoxLayout(status_panel)
        status_l.setContentsMargins(14, 10, 14, 10)
        self.status = QLabel("Ready when you are. Choose a search type to get started.")
        self.status.setObjectName("Muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress.setMaximumWidth(170)
        self.progress.setTextVisible(False)
        status_l.addWidget(self.status, 1)
        status_l.addWidget(self.progress)
        content.addWidget(status_panel)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.gallery = QWidget()
        self.gallery.setStyleSheet("background:transparent;")
        self.grid = QGridLayout(self.gallery)
        self.grid.setContentsMargins(2, 2, 8, 8)
        self.grid.setHorizontalSpacing(13)
        self.grid.setVerticalSpacing(13)
        self.scroll.setWidget(self.gallery)
        self.scroll.verticalScrollBar().valueChanged.connect(self.on_gallery_scroll)
        content.addWidget(self.scroll, 1)

        footer = QHBoxLayout()
        self.footer_hint = QLabel("YOUTUBE DATA API  ·  POPULAR LONG-FORM VIDEOS")
        self.footer_hint.setObjectName("Eyebrow")
        footer.addWidget(self.footer_hint)
        footer.addStretch()
        auto_hint = QLabel("AUTO-LOAD ON SCROLL")
        auto_hint.setObjectName("Eyebrow")
        footer.addWidget(auto_hint)
        content.addLayout(footer)
        body.addLayout(content, 1)
        root.addLayout(body, 1)

        self.mode.setCurrentIndex(1)
        self.update_placeholders()
        self.show_empty_state()

    def show_empty_state(self):
        self.empty_state = QFrame()
        self.empty_state.setObjectName("Panel")
        self.empty_state.setMinimumHeight(250)
        box = QVBoxLayout(self.empty_state)
        box.setAlignment(Qt.AlignCenter)
        icon = QLabel("▧")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:34pt;color:#8175eb;background:transparent;")
        title = QLabel("Your inspiration starts here")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:15pt;font-weight:800;background:transparent;")
        desc = QLabel("Search popular videos by actor, explore a topic, or choose a thumbnail to find visually similar results.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setObjectName("Muted")
        box.addWidget(icon)
        box.addWidget(title)
        box.addWidget(desc)
        self.grid.addWidget(self.empty_state, 0, 0, 1, 4)

    def update_placeholders(self):
        idx = self.mode.currentIndex()
        self.actor.setVisible(idx == 0)
        self.topic.setVisible(idx == 1)
        self.image_preview.setVisible(idx == 2)
        self.image_btn.setVisible(idx == 2)

    def choose_reference_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose reference thumbnail", "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        self.actor_image_path = path
        pix = QPixmap(path)
        if not pix.isNull():
            self.image_preview.setPixmap(pix.scaled(
                58, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.image_preview.setToolTip(path)
        else:
            self.image_preview.setText(Path(path).name)

    def apply_theme(self):
        QApplication.instance().setStyleSheet(DARK if self.dark else LIGHT)
        self.theme_btn.setText("☀  Light mode" if self.dark else "☾  Dark mode")

    def toggle_theme(self):
        self.dark = not self.dark
        self.config["dark"] = self.dark; save_config(self.config)
        self.apply_theme()

    def open_settings(self):
        d = SettingsDialog(self, self.download_dir)
        if d.exec():
            self.download_dir = Path(d.download_path.text().strip()).expanduser()
            self.config["download_dir"] = str(self.download_dir)
            save_config(self.config)
            self.status.setText("Settings saved locally.")

    def selected_min_minutes(self):
        index = self.duration_choice.currentIndex()
        return (30, 40, 50)[index] if index < 3 else self.custom_minutes.value()

    def make_query(self):
        mode = self.mode.currentIndex()
        if mode == 0:
            actor = self.actor.text().strip()
            if not actor:
                raise ValueError("Enter an actor name.")
            return actor, ""
        if mode == 1:
            topic = self.topic.text().strip()
            if not topic:
                raise ValueError("Enter a topic or keyword.")
            return topic, ""
        if not self.actor_image_path:
            raise ValueError("Choose a reference thumbnail image first.")
        return "", self.actor_image_path

    def start_search(self):
        try: query, image_path = self.make_query()
        except ValueError as e:
            QMessageBox.warning(self,"Missing search input",str(e)); return
        self.last_query = query
        self.search_image_path = image_path
        self.search_folder_name = query or ("similar_thumbnails_" + Path(image_path).stem)
        self.min_duration_minutes = self.selected_min_minutes()
        self.config["min_duration_minutes"] = self.min_duration_minutes
        save_config(self.config)
        self.next_token = ""; self.seen_ids.clear(); self.pending_items=[]; self.current_batch=[]
        self.loading_more = False; self.has_more_pages = False
        self.clear_gallery()
        self._visible_cards = []
        self.run_search("")

    def next_batch(self):
        if self.loading_more or not self.has_more_pages:
            return
        limit = BATCH_SIZE
        if len(self.pending_items) >= limit:
            self.show_next_results()
        elif self.next_token:
            self.run_search(self.next_token)
        else:
            self.has_more_pages = False

    def run_search(self, token):
        self.loading_more = True
        self.search_btn.setEnabled(False)
        self.progress.show()
        self.status.setText(f"Searching popular videos ({self.min_duration_minutes} min+)…")
        worker = SearchWorker(self.api_key, self.last_query, token, BATCH_SIZE,
                              self.min_duration_minutes, self.search_image_path)
        worker.signals.finished.connect(self.search_finished)
        worker.signals.progress.connect(self.status.setText)
        self.pool.start(worker)

    def search_finished(self, data, error):
        self.progress.hide(); self.search_btn.setEnabled(True)
        self.loading_more = False
        if error:
            self.has_more_pages = False
            self.status.setText("Search failed.")
            QMessageBox.critical(self,"YouTube search error",error+"\n\nCheck your internet connection and YouTube API configuration/quota.")
            return
        known = self.seen_ids | {x["id"] for x in self.pending_items}
        self.pending_items.extend(x for x in data["items"] if x["id"] not in known)
        self.next_token = data["next"]
        self.has_more_pages = bool(self.pending_items or self.next_token)
        if len(self.pending_items) >= BATCH_SIZE or not self.next_token:
            self.show_next_results()
        else:
            self.run_search(self.next_token)

    def show_next_results(self):
        fresh=self.pending_items[:BATCH_SIZE]
        self.pending_items=self.pending_items[BATCH_SIZE:]
        self.seen_ids.update(x["id"] for x in fresh)
        self.add_cards(fresh)
        mode_name = ("similar thumbnails" if self.search_image_path else
                     ("actor videos" if self.mode.currentIndex() == 0 else "topic videos"))
        self.result_label.setText(f"{len(self.seen_ids)} {mode_name} found  ·  popular videos first")
        self.status.setText(f"Showing {len(fresh)} popular videos ({self.min_duration_minutes} min+). Scroll for more.")
        self.download_all_btn.setEnabled(bool(self.seen_ids))
        self.has_more_pages = bool(self.pending_items or self.next_token)
        if not fresh and self.next_token:
            self.run_search(self.next_token)
        elif not fresh and not self.seen_ids:
            self.status.setText("No matching videos found. Try another search or a shorter minimum duration.")
            self.result_label.setText("No matching videos found")
            empty = QFrame(); empty.setObjectName("Panel")
            box = QVBoxLayout(empty); box.setAlignment(Qt.AlignCenter)
            title = QLabel("No thumbnails found this time")
            title.setStyleSheet("font-size:14pt;font-weight:800;background:transparent;")
            detail = QLabel("Try a broader actor or topic, a different reference image, or a shorter duration filter.")
            detail.setWordWrap(True); detail.setAlignment(Qt.AlignCenter); detail.setObjectName("Muted")
            box.addWidget(title); box.addWidget(detail)
            self.grid.addWidget(empty, 0, 0, 1, 4)
        QTimer.singleShot(180, self.try_auto_load)

    def try_auto_load(self):
        if not self.has_more_pages or self.loading_more or not self.auto_load_enabled:
            return
        bar = self.scroll.verticalScrollBar()
        # Fill a short viewport automatically; otherwise load when near its bottom.
        if bar.maximum() == 0 or bar.maximum() - bar.value() <= max(100, int(bar.pageStep() * 0.22)):
            self.next_batch()

    def clear_gallery(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.result_label.setText("Searching for popular long-form videos…")
        self.download_all_btn.setEnabled(False)

    def add_cards(self, items):
        self._visible_cards = getattr(self, "_visible_cards", [])
        self._visible_cards.extend(ThumbCard(item, self) for item in items)
        self.reflow_gallery()
        self.current_batch = items

    def reflow_gallery(self):
        cards = getattr(self, "_visible_cards", [])
        if not cards:
            return
        while self.grid.count():
            item = self.grid.takeAt(0)
            # Keep the widgets alive while moving them to their new positions.
        width = max(500, self.scroll.viewport().width())
        columns = max(1, min(4, width // 275))
        for col in range(4):
            self.grid.setColumnStretch(col, 1 if col < columns else 0)
        for i, card in enumerate(cards):
            self.grid.addWidget(card, i // columns, i % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_visible_cards"):
            self.reflow_gallery()

    def download_item(self, item):
        self.start_download([item])
    def download_all(self):
        items=[card.item for card in getattr(self, "_visible_cards", [])]
        if items: self.start_download(items)
    def start_download(self, items):
        folder=self.download_dir/self.safe_name(self.search_folder_name or self.last_query or "similar_thumbnails")
        worker=DownloadWorker(items,folder); self.download_workers.append(worker)
        worker.signals.done.connect(self.download_finished)
        worker.signals.done.connect(lambda _a, _b, w=worker: self.download_workers.remove(w) if w in self.download_workers else None)
        self.status.setText("Downloading thumbnails in background…")
        self.pool.start(worker)
    def download_finished(self, message, error):
        self.status.setText(message)
        if error:
            QMessageBox.warning(self, "Download failed", error)
        else:
            folder = self.download_dir / self.safe_name(
                self.search_folder_name or self.last_query or "similar_thumbnails")
            QMessageBox.information(self, "Download complete", f"{message}\nSaved to:\n{folder}")

    def on_gallery_scroll(self, value):
        if self.loading_more or not self.auto_load_enabled or not self.has_more_pages:
            return
        bar=self.scroll.verticalScrollBar()
        if bar.maximum() > 0:
            threshold=min(260,max(100,int(bar.pageStep()*0.22)))
            if bar.maximum()-value <= threshold:
                self.next_batch()

    @staticmethod
    def safe_name(value):
        return "".join(c for c in value if c.isalnum() or c in " -_").strip().replace(" ","_")[:80]

def make_splash():
    pix=QPixmap(520,300); pix.fill(QColor("#17192a")); painter=QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#6657e8")); painter.setPen(Qt.NoPen); painter.drawRoundedRect(218,48,84,84,24,24)
    painter.setPen(QColor("white")); painter.setFont(QFont("Segoe UI",34,QFont.Bold)); painter.drawText(218,110,84,45,Qt.AlignCenter,"✦")
    painter.setFont(QFont("Segoe UI",25,QFont.Bold)); painter.drawText(0,178,520,42,Qt.AlignCenter,"Thumb Finder")
    painter.setPen(QColor("#b8bdd0")); painter.setFont(QFont("Segoe UI",10)); painter.drawText(0,214,520,28,Qt.AlignCenter,"Discover. Explore. Get Inspired.")
    painter.setPen(QColor("#8b80ff")); painter.drawText(0,264,520,20,Qt.AlignCenter,"Preparing your workspace…")
    painter.end(); return pix

def main():
    app=QApplication(sys.argv); app.setApplicationName(APP_NAME)
    icon_path=Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app_icon.svg"
    if icon_path.exists(): app.setWindowIcon(QIcon(str(icon_path)))
    splash=QSplashScreen(make_splash()); splash.show(); app.processEvents()
    window=MainWindow()
    if not window.run_first_launch_setup():
        splash.close()
        return
    QTimer.singleShot(500, lambda:(window.show(),splash.finish(window)))
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
