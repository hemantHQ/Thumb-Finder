import os, sys, json, requests, logging, re, threading, tempfile
from pathlib import Path
from .utils import parse_youtube_duration
from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QUrl, QSize, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QDesktopServices, QIcon
from PySide6.QtWidgets import QGraphicsOpacityEffect
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QSpinBox, QFrame, QScrollArea,
    QGridLayout, QFileDialog, QMessageBox, QProgressBar, QDialog, QSplitter, QSizePolicy,
    QFormLayout, QDialogButtonBox, QCheckBox, QInputDialog
)

# OpenCV and NumPy are intentionally lazy-loaded. Normal startup/search should not
# pay their import cost; they are needed only for similar-thumbnail image search.
cv2 = None
np = None
CV_AVAILABLE = None

def ensure_cv_available():
    global cv2, np, CV_AVAILABLE
    if CV_AVAILABLE is True:
        return True
    if CV_AVAILABLE is False:
        return False
    try:
        import cv2 as _cv2
        import numpy as _np
        cv2, np = _cv2, _np
        CV_AVAILABLE = True
        logging.info("OpenCV image-search dependencies loaded on demand")
        return True
    except Exception:
        CV_AVAILABLE = False
        logging.exception("Could not load OpenCV/NumPy for similar-image search")
        return False

try:
    from .version import __version__
except ImportError:
    try:
        from thumb_finder.version import __version__
    except ImportError:
        from version import __version__

APP_NAME = "Thumb Finder"
APP_VERSION = __version__

from .release_control import fetch_release_control, evaluate_release



def load_youtube_api_key():
    """Load an optional developer-provided environment key; otherwise ask at runtime."""
    return os.environ.get("THUMB_FINDER_YOUTUBE_API_KEY", "").strip()


LOG_PATH = None


def configure_logging():
    """Configure rotating diagnostics in a writable user/temp directory."""
    global LOG_PATH
    candidates = [Path.home() / ".thumb_finder" / "logs",
                  Path(os.environ.get("TEMP", "/tmp")) / "ThumbFinder" / "logs"]
    for directory in candidates:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            log_path = directory / "thumb_finder.log"
            from logging.handlers import RotatingFileHandler
            root = logging.getLogger()
            root.setLevel(logging.INFO)
            if not any(getattr(h, "baseFilename", None) == str(log_path) for h in root.handlers):
                handler = RotatingFileHandler(log_path, maxBytes=2_000_000,
                                              backupCount=3, encoding="utf-8")
                handler.setFormatter(logging.Formatter(
                    "%(asctime)s %(levelname)s %(threadName)s %(message)s"))
                root.addHandler(handler)
            LOG_PATH = log_path
            return log_path
        except Exception:
            continue
    logging.basicConfig(level=logging.INFO)
    LOG_PATH = None
    return None


def handle_unhandled_exception(exc_type, exc_value, exc_tb):
    """Log unexpected crashes and show a useful message instead of failing silently."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logging.critical(
        "Unhandled application exception",
        exc_info=(exc_type, exc_value, exc_tb),
    )
    app = QApplication.instance()
    if app is not None:
        try:
            QMessageBox.critical(
                None,
                "Thumb Finder encountered an error",
                "An unexpected error occurred. Diagnostic details were written to the log when possible.\n\n"
                f"Error: {exc_value}\n\n"
                f"Log file: {LOG_PATH or 'Unavailable (see console output)'}",
            )
        except Exception:
            logging.exception("Could not display the unexpected-error dialog")

CONFIG_PATH = Path.home() / ".thumb_finder" / "config.json"
DOWNLOAD_ROOT = Path.home() / "Pictures" / "Thumb Finder"
BATCH_SIZE = 20  # Results are loaded automatically as the gallery is scrolled.

# Compact search bar used while browsing the gallery.
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
QPushButton#ThemeToggle { min-width:94px; padding:9px 10px; border-radius:12px; font-weight:750; }
QPushButton#ThemeToggle { background:#282a40; color:#f4f3fb; border:1px solid #454762; }
QPushButton#ThemeToggle:hover { background:#353752; }
QPushButton#CompactSearch { background:#20243a; color:#f5f4ff; border:1px solid #363b58; border-radius:12px; font-weight:700; }
QDialog { background:#171827; }
QDialogButtonBox QPushButton { min-width:95px; }

QWidget#AppCanvas { background:#0d0f18; }
QLabel#BrandTitle { font-size:18pt; font-weight:850; color:#f8f7ff; background:transparent; }
QLabel#BrandSubtitle { font-size:7.5pt; letter-spacing:1.5px; font-weight:800; color:#8884b6; background:transparent; }
QLabel#HeroTitle { font-size:25pt; font-weight:850; color:#fbfaff; background:transparent; }
QLabel#HeroSubtitle { color:#a3a4ba; font-size:10pt; background:transparent; }
QLabel#DurationChip { background:#24213d; border:1px solid #49416f; color:#bdb4ff; border-radius:10px; padding:6px 12px; font-weight:800; font-size:8.5pt; }
QFrame#SearchPanel { background:#171a29; border:1px solid #2b2e45; border-radius:20px; }
QLabel#PanelEyebrow { color:#9d94ff; font-size:8pt; font-weight:850; letter-spacing:1.2px; background:transparent; }
QComboBox#ModeSelector, QComboBox#GenreSelector, QLineEdit#SearchInput { background:#20243a; color:#f5f4ff; border:1px solid #363b58; border-radius:12px; padding:11px 14px; }
QComboBox#ModeSelector:focus, QComboBox#GenreSelector:focus, QLineEdit#SearchInput:focus { border:1px solid #8175f2; }
QLabel#ImageDropZone { background:#20243a; color:#a7a8bf; border:1px dashed #575b7a; border-radius:13px; padding:10px; }
QPushButton#PrimarySearch { background:#705ff0; color:#fff; border:0; border-radius:12px; padding:12px 18px; font-weight:850; }
QPushButton#PrimarySearch:hover { background:#8173ff; }
QPushButton#ToolbarButton { background:#22263b; color:#e9e8fa; border:1px solid #3a3e5b; border-radius:12px; padding:10px 14px; font-weight:750; }
QPushButton#ToolbarButton:hover { background:#2e3350; border-color:#6962a7; }
QPushButton#ThemeToggle { min-width:44px; max-width:44px; min-height:44px; max-height:44px; padding:0; border-radius:12px; background:#22263b; color:#f7f4ff; border:1px solid #3a3e5b; font-size:17pt; }
QLabel#SectionHeading { font-size:17pt; font-weight:850; color:#f8f7ff; background:transparent; }
QFrame#StatusPanel { background:#171a29; border:1px solid #2b2e45; border-radius:13px; }
QWidget#GalleryCanvas { background:transparent; }
QLabel#FooterLabel { color:#817fa1; font-size:7.5pt; font-weight:800; letter-spacing:1px; background:transparent; }
QLabel#FooterSignature { color:#9b9cb2; font-size:8pt; font-weight:700; background:transparent; }
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
QPushButton#ThemeToggle { background:#ffffff; color:#393653; border:1px solid #dfe1ed; }
QPushButton#ThemeToggle:hover { background:#f0effa; }
QPushButton#CompactSearch { background:#f9f9fe; color:#25243d; border:1px solid #dfe1ed; border-radius:12px; font-weight:700; }
QDialog { background:#fff; }
QDialogButtonBox QPushButton { min-width:95px; }

QWidget#AppCanvas { background:#f4f5fb; }
QLabel#BrandTitle { font-size:18pt; font-weight:850; color:#25243b; background:transparent; }
QLabel#BrandSubtitle { font-size:7.5pt; letter-spacing:1.5px; font-weight:800; color:#77739c; background:transparent; }
QLabel#HeroTitle { font-size:25pt; font-weight:850; color:#22223a; background:transparent; }
QLabel#HeroSubtitle { color:#686b82; font-size:10pt; background:transparent; }
QLabel#DurationChip { background:#eeecff; border:1px solid #dcd7ff; color:#594cc4; border-radius:10px; padding:6px 12px; font-weight:800; font-size:8.5pt; }
QFrame#SearchPanel { background:#ffffff; border:1px solid #e2e4ef; border-radius:20px; }
QLabel#PanelEyebrow { color:#6657d9; font-size:8pt; font-weight:850; letter-spacing:1.2px; background:transparent; }
QComboBox#ModeSelector, QComboBox#GenreSelector, QLineEdit#SearchInput { background:#f9f9fe; color:#25243d; border:1px solid #dfe1ed; border-radius:12px; padding:11px 14px; }
QComboBox#ModeSelector:focus, QComboBox#GenreSelector:focus, QLineEdit#SearchInput:focus { border:1px solid #8175eb; background:#fff; }
QLabel#ImageDropZone { background:#fafaff; color:#6d7088; border:1px dashed #c9c9df; border-radius:13px; padding:10px; }
QPushButton#PrimarySearch { background:#6657e8; color:#fff; border:0; border-radius:12px; padding:12px 18px; font-weight:850; }
QPushButton#PrimarySearch:hover { background:#796cf2; }
QPushButton#ToolbarButton { background:#fff; color:#393653; border:1px solid #dedfed; border-radius:12px; padding:10px 14px; font-weight:750; }
QPushButton#ToolbarButton:hover { background:#f0effa; border-color:#c9c4ed; }
QPushButton#ThemeToggle { min-width:44px; max-width:44px; min-height:44px; max-height:44px; padding:0; border-radius:12px; background:#fff; color:#393653; border:1px solid #dedfed; font-size:17pt; }
QLabel#SectionHeading { font-size:17pt; font-weight:850; color:#25243b; background:transparent; }
QFrame#StatusPanel { background:#fff; border:1px solid #e2e4ef; border-radius:13px; }
QWidget#GalleryCanvas { background:transparent; }
QLabel#FooterLabel { color:#85869a; font-size:7.5pt; font-weight:800; letter-spacing:1px; background:transparent; }
QLabel#FooterSignature { color:#73758b; font-size:8pt; font-weight:700; background:transparent; }
"""

def load_config():
    try:
        if not CONFIG_PATH.exists():
            return {}
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logging.exception("Could not read settings file; using safe defaults")
        return {}

def save_config(data):
    """Atomically save local settings; return False instead of crashing a UI slot."""
    temporary = CONFIG_PATH.with_suffix(".json.tmp")
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temporary, CONFIG_PATH)
        return True
    except Exception:
        logging.exception("Could not save application settings")
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logging.exception("Could not remove incomplete settings temp file")
        return False


class WorkerSignals(QObject):
    finished = Signal(object, object)
    progress = Signal(str)

class SearchWorker(QRunnable):
    """Fetch YouTube videos from the original search phrase; image mode compares thumbnails locally."""
    def __init__(self, api_key, query, page_token="", batch_size=BATCH_SIZE,
                 min_minutes=40, reference_image="", movie_genre="Any genre",
                 ):
        super().__init__()
        self.signals = WorkerSignals()
        self.api_key, self.query, self.page_token = api_key, query, page_token
        self.batch_size = batch_size
        self.min_seconds = int(min_minutes) * 60
        self.reference_image = reference_image
        self.image_mode = bool(reference_image)
        self.movie_genre = movie_genre

    @staticmethod
    def duration_seconds(value):
        return parse_youtube_duration(value)

    @staticmethod
    def _visual_signature(image_bytes):
        if not image_bytes or not ensure_cv_available():
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
        orb = cv2.ORB_create(nfeatures=450, scaleFactor=1.2, nlevels=6)
        _keypoints, descriptors = orb.detectAndCompute(gray, None)
        return hist, dhash, descriptors

    @staticmethod
    def _similarity(a, b):
        if a is None or b is None or not ensure_cv_available():
            return 0.0
        hist_score = max(0.0, float(cv2.compareHist(a[0], b[0], cv2.HISTCMP_CORREL)))
        hash_score = 1.0 - float(np.count_nonzero(a[1] != b[1])) / 64.0
        feature_score = 0.0
        if a[2] is not None and b[2] is not None and len(a[2]) >= 4 and len(b[2]) >= 4:
            matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = matcher.match(a[2], b[2])
            good = sum(1 for m in matches if m.distance < 58)
            feature_score = min(1.0, good / max(12.0, min(len(a[2]), len(b[2])) * 0.18))
        return max(0.0, min(1.0, 0.40 * hist_score + 0.25 * hash_score + 0.35 * feature_score))

    def run(self):
        try:
            reference_signature = None
            if self.image_mode:
                if not ensure_cv_available():
                    raise RuntimeError("Similar-image search needs OpenCV and NumPy. Install the project dependencies using the instructions in DEBUGGING.md.")
                reference_bytes = Path(self.reference_image).read_bytes()
                reference_signature = self._visual_signature(reference_bytes)
                if reference_signature is None:
                    raise RuntimeError("The selected reference image could not be read.")

            search_query = self.query
            token = self.page_token
            results, visited = [], set()
            next_token = token
            pages_checked = 0
            # Bound each fetch pass so the UI gets a batch quickly and API quota is controlled.
            # Further pages are fetched only when the user scrolls for more.
            max_pages = 5
            while len(results) < self.batch_size and pages_checked < max_pages:
                self.signals.progress.emit(
                    f"Finding popular movies… {len(results)}/{self.batch_size}")
                params = {"part": "snippet", "type": "video", "maxResults": 50,
                          "order": "viewCount", "videoDuration": "long", "key": self.api_key,
}
                # YouTube exposes broad video categories, not reliable movie-genre metadata.
                # Genre selection is therefore applied as search keywords, then duration-filtered.
                query_parts = [search_query.strip()] if search_query.strip() else []
                if self.movie_genre and self.movie_genre != "Any genre":
                    query_parts.append(self.movie_genre.lower())
                if self.image_mode and not query_parts:
                    query_parts.append("full movie")
                elif query_parts and not any("movie" in q.lower() or "film" in q.lower() for q in query_parts):
                    query_parts.append("movie")
                if query_parts:
                    params["q"] = " ".join(query_parts)
                if token:
                    params["pageToken"] = token
                r = requests.get("https://www.googleapis.com/youtube/v3/search",
                                 params=params, timeout=(5, 20))
                r.raise_for_status()
                payload = r.json()
                raw = payload.get("items", [])
                ids = [x.get("id", {}).get("videoId") for x in raw]
                ids = [x for x in ids if x and x not in visited]
                visited.update(ids)
                details = {}
                if ids:
                    self.signals.progress.emit("Checking movie duration and popularity…")
                    vr = requests.get("https://www.googleapis.com/youtube/v3/videos",
                        params={"part": "contentDetails,statistics", "id": ",".join(ids),
                                "key": self.api_key}, timeout=(5, 20))
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
                            tr = requests.get(best, timeout=(5, 12))
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
                    # Keep the token so another bounded page batch can load on scroll.
                    break
                token = next_token
            # In every mode, popular videos are shown first.
            if self.image_mode:
                results.sort(key=lambda x: (x.get("similarity", 0), x["views"]), reverse=True)
            else:
                results.sort(key=lambda x: x["views"], reverse=True)
            self.signals.finished.emit({"items": results, "next": next_token}, None)
        except Exception as e:
            logging.exception("Movie search worker failed")
            message = str(e)
            response = getattr(e, "response", None)
            if response is not None:
                try:
                    payload = response.json()
                    message = payload.get("error", {}).get("message") or message
                except Exception:
                    pass
            self.signals.finished.emit(None, message)

class ImageSignals(QObject):
    done = Signal(bytes)

class DownloadSignals(QObject):
    done = Signal(str, str)

class DownloadWorker(QRunnable):
    def __init__(self, items, folder):
        super().__init__()
        self.items = items
        self.folder = folder
        self.signals = DownloadSignals()

    def run(self):
        saved, failed = 0, 0
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            for item in self.items:
                try:
                    if not item.get("thumbnail"):
                        failed += 1
                        continue
                    response = requests.get(item["thumbnail"], timeout=(5, 20))
                    response.raise_for_status()
                    safe_title = "".join(
                        c for c in item.get("title", "thumbnail")
                        if c.isalnum() or c in " -_").strip().replace(" ", "_")[:75]
                    name = safe_title or item.get("id", "thumbnail")
                    from PIL import Image
                    from io import BytesIO
                    target = self.folder / f"{name}_{item.get('id', saved)}.jpg"
                    with Image.open(BytesIO(response.content)) as source:
                        source.convert("RGB").save(target, format="JPEG", quality=95, optimize=True)
                    saved += 1
                except Exception:
                    failed += 1
                    logging.exception("Could not download thumbnail for video %s", item.get("id"))
            summary = f"Downloaded {saved} thumbnail(s)."
            if failed:
                summary += f" {failed} failed. See the log for details."
            self.signals.done.emit(summary, "" if saved else "No thumbnails could be downloaded.")
        except Exception as exc:
            logging.exception("Thumbnail download batch failed")
            self.signals.done.emit("Download failed.", str(exc))


class ImageWorker(QRunnable):
    def __init__(self, url):
        super().__init__(); self.url=url; self.signals=ImageSignals()
    def run(self):
        try:
            r=requests.get(self.url,timeout=(5, 12)); r.raise_for_status(); self.signals.done.emit(r.content)
        except Exception:
            logging.exception("Thumbnail preview download failed: %s", self.url)
            self.signals.done.emit(b"")

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
        note = QLabel("Your YouTube Data API key is stored locally in your user profile. Keep it private; it is not uploaded to Thumb Finder or GitHub.")
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
        fade = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(fade)
        fade.setOpacity(0.0)
        self._fade_animation = QPropertyAnimation(fade, b"opacity", self)
        self._fade_animation.setDuration(220)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_animation.start()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.image = QLabel("Loading preview…")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumHeight(165)
        self.image.setMaximumHeight(230)
        self.image.setStyleSheet("background:rgba(120,120,140,0.12); border-radius:11px;")
        self.image.setMouseTracking(True)
        self._image_hover_animation = None
        layout.addWidget(self.image)

        title = QLabel(item["title"])
        title.setWordWrap(True)
        title.setMinimumHeight(40)
        title.setMaximumHeight(48)
        title.setStyleSheet("font-size:10pt;font-weight:700;background:transparent;border:0;")
        title.setToolTip(item["title"])
        layout.addWidget(title)

        views = QLabel(f"◉  {item['views']:,} views")
        views.setStyleSheet("font-weight:700;background:transparent;border:0;")
        layout.addWidget(views)
        if item.get("similarity") is not None:
            match = QLabel(f"▧  Visual match · {item['similarity'] * 100:.0f}%")
            match.setStyleSheet("font-weight:700;background:transparent;border:0;")
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
        editb = QPushButton("✎  Edit")
        editb.setObjectName("Secondary")
        editb.setProperty("class", "secondary")
        editb.setStyleSheet("padding:8px 10px;font-size:9pt;")
        editb.clicked.connect(lambda: parent.open_thumbnail_editor(item))
        row.addWidget(dl, 1); row.addWidget(openb, 1); row.addWidget(editb, 1)
        layout.addLayout(row)

        if item.get("thumbnail"):
            worker = ImageWorker(item["thumbnail"])
            worker.signals.done.connect(self.set_image)
            parent.image_workers.append(worker)
            worker.signals.done.connect(lambda _data, w=worker: parent.image_workers.remove(w) if w in parent.image_workers else None)
            parent.pool.start(worker)

    def _animate_thumbnail(self, hovered):
        target = 190 if hovered else 165
        if self._image_hover_animation is not None:
            self._image_hover_animation.stop()
        animation = QPropertyAnimation(self.image, b"minimumHeight", self)
        animation.setDuration(190)
        animation.setStartValue(self.image.minimumHeight())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._image_hover_animation = animation
        animation.start()

    def enterEvent(self, event):
        self._animate_thumbnail(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_thumbnail(False)
        super().leaveEvent(event)

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
        self.api_key = load_youtube_api_key() or str(self.config.get("youtube_api_key", "")).strip()
        try:
            configured_download_dir = self.config.get("download_dir", str(DOWNLOAD_ROOT))
            self.download_dir = Path(configured_download_dir).expanduser()
        except (TypeError, ValueError, OSError):
            logging.exception("Invalid saved download directory; using default")
            self.download_dir = DOWNLOAD_ROOT
        self.config.pop("search_language", None)
        self.theme_preference = self.config.get("theme", "system")
        if self.theme_preference not in ("system", "dark", "light"):
            # Migrate older builds that stored a boolean dark setting.
            self.theme_preference = "dark" if self.config.get("dark", False) else "system"
        self.dark = self.resolve_system_dark() if self.theme_preference == "system" else self.theme_preference == "dark"
        self.next_token = ""
        self.last_query = ""
        self.loading_more = False
        self.auto_load_enabled = True
        self.has_more_pages = False
        try:
            self.min_duration_minutes = int(self.config.get("min_duration_minutes", 40))
        except (TypeError, ValueError):
            logging.exception("Invalid saved minimum duration; using 40 minutes")
            self.min_duration_minutes = 40
        self.min_duration_minutes = max(40, min(360, self.min_duration_minutes))
        self.movie_genre = self.config.get("movie_genre", "Any genre")
        if not isinstance(self.movie_genre, str):
            self.movie_genre = "Any genre"
        self.search_folder_name = ""
        self.search_image_path = ""
        self.seen_ids = set()
        self.pool = QThreadPool.globalInstance()
        self.search_workers = []
        self.image_workers = []
        self.download_workers = []
        self._visible_cards = []
        self.setWindowTitle("Thumb Finder")
        resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
        icon_path = resource_root / ("app_icon.ico" if sys.platform == "win32" else "app_icon.icns")
        if not icon_path.exists():
            icon_path = resource_root / "app_icon.svg"
        self.app_icon_path = icon_path if icon_path.exists() else None
        if self.app_icon_path:
            self.setWindowIcon(QIcon(str(self.app_icon_path)))
        self.setMinimumSize(480,520)
        self.resize(1240,860)
        self.build_ui()
        self.apply_theme()

    def run_first_launch_setup(self):
        """Prepare writable user folders; never contact GitHub in local debug mode."""
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
            self.config.setdefault("setup_complete", True)
            self.config.setdefault("download_dir", str(self.download_dir))
            if not save_config(self.config):
                self.status.setText("Settings could not be saved; check user-folder permissions.")
            return True
        except Exception as exc:
            logging.exception("First-launch setup failed")
            QMessageBox.critical(
                self, "Setup error",
                f"Thumb Finder could not prepare its user folders.\n\n{exc}"
            )
            return False

    def prompt_for_api_key(self):
        """Ask for a key only after the main window is visible, keeping launch responsive."""
        if self.api_key:
            self.search_btn.setEnabled(True)
            return True
        self.search_btn.setEnabled(False)
        self.status.setText("YouTube API key required before searching.")
        key, accepted = QInputDialog.getText(
            self, "YouTube Data API key",
            "Enter your YouTube Data API key to use movie search:",
            QLineEdit.Password,
        )
        key = key.strip()
        if not accepted or not key:
            self.status.setText("Add your YouTube API key to start searching.")
            return False
        if not key:
            self.status.setText("No API key entered. Search remains disabled until a key is provided.")
            return False
        self.api_key = key
        self.config["youtube_api_key"] = key
        if not save_config(self.config):
            self.api_key = ""
            self.config.pop("youtube_api_key", None)
            QMessageBox.warning(
                self, "Could not save API key",
                "The key was entered but could not be saved. Check folder permissions and try again."
            )
            return False
        self.search_btn.setEnabled(True)
        self.status.setText("API key saved locally. Ready to search.")
        logging.info("YouTube API key saved to local user settings")
        return True

    def build_ui(self):
        """Build the redesigned local-first discovery workspace."""
        central = QWidget()
        central.setObjectName("AppCanvas")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(18)

        # Top navigation / brand bar (can collapse while browsing results)
        self.top_widget = QWidget()
        top = QHBoxLayout(self.top_widget)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(12)
        logo = QLabel()
        logo.setFixedSize(46, 46)
        logo.setAlignment(Qt.AlignCenter)
        if self.app_icon_path:
            logo.setPixmap(QIcon(str(self.app_icon_path)).pixmap(QSize(46, 46)))
        else:
            logo.setText("✦")
            logo.setStyleSheet(
                "background:#6657e8;color:white;border-radius:14px;"
                "font-size:23pt;font-weight:800;"
            )
        top.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel("Thumb Finder")
        brand.setObjectName("BrandTitle")
        strap = QLabel("YOUTUBE THUMBNAIL TOOLS")
        strap.setObjectName("BrandSubtitle")
        brand_col.addWidget(brand)
        brand_col.addWidget(strap)
        top.addLayout(brand_col)
        top.addStretch(1)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ThemeToggle")
        self.theme_btn.setFixedSize(44, 44)
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setToolTip("Switch light or dark appearance")
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.update_theme_button()
        settings = QPushButton("⚙  Settings")
        settings.setObjectName("ToolbarButton")
        settings.setCursor(Qt.PointingHandCursor)
        settings.clicked.connect(self.open_settings)
        top.addWidget(self.theme_btn)
        top.addWidget(settings)
        root.addWidget(self.top_widget)

        # Hero heading
        self.hero_widget = QWidget()
        hero = QHBoxLayout(self.hero_widget)
        hero.setContentsMargins(0, 0, 0, 0)
        hero_col = QVBoxLayout()
        hero_col.setSpacing(3)
        # Keep the hero container out of the way; the search and gallery are the focus.
        self.hero_widget.setVisible(False)

        # Search console: compact, full-width card with all modes.
        search_panel = QFrame()
        self.search_panel = search_panel
        search_panel.setObjectName("SearchPanel")
        search_outer = QVBoxLayout(search_panel)
        search_outer.setContentsMargins(20, 18, 20, 18)
        self.search_panel_layout = search_outer
        search_outer.setSpacing(13)

        search_top = QHBoxLayout()
        search_label = QLabel("SEARCH MODE")
        search_label.setObjectName("PanelEyebrow")
        search_top.addWidget(search_label)
        search_top.addStretch()
        self.mode_hint = QLabel("Search by actor, topic or reference thumbnail")
        self.mode_hint.setObjectName("Muted")
        search_top.addWidget(self.mode_hint)
        self.search_top_widget = QWidget()
        self.search_top_widget.setLayout(search_top)
        search_outer.addWidget(self.search_top_widget)

        self.compact_search_btn = QPushButton("⌕   Search thumbnails   ·   Tap to expand")
        self.compact_search_btn.setObjectName("CompactSearch")
        self.compact_search_btn.setMinimumHeight(42)
        self.compact_search_btn.clicked.connect(lambda: self.set_browse_compact(False))
        self.compact_search_btn.hide()
        search_outer.addWidget(self.compact_search_btn)

        self.mode = QComboBox()
        self.mode.setObjectName("ModeSelector")
        self.mode.addItems([
            "⌕   Search",
            "▧   Via photo",
        ])
        self.mode.setMinimumHeight(44)
        self.mode.setToolTip("Search by actor, movie title, topic or keyword, or find visually similar thumbnails from a photo.")
        self.mode.currentIndexChanged.connect(self.update_placeholders)
        search_outer.addWidget(self.mode)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Enter an actor, movie title or topic…")
        self.search_input.setMinimumHeight(48)
        self.search_input.returnPressed.connect(self.start_search)
        search_outer.addWidget(self.search_input)
        self.actor = self.search_input
        self.topic = self.search_input

        self.image_row_widget = QWidget()
        self.image_row = QHBoxLayout(self.image_row_widget)
        self.image_row.setContentsMargins(0, 0, 0, 0)
        self.image_row.setSpacing(12)
        self.image_preview = QLabel(
            "Choose a reference thumbnail to find visually similar movie artwork."
        )
        self.image_preview.setObjectName("ImageDropZone")
        self.image_preview.setMinimumHeight(64)
        self.image_preview.setWordWrap(True)
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_btn = QPushButton("▧   Choose image")
        self.image_btn.setObjectName("ToolbarButton")
        self.image_btn.setMinimumHeight(44)
        self.image_btn.setCursor(Qt.PointingHandCursor)
        self.image_btn.clicked.connect(self.choose_reference_image)
        self.image_row.addWidget(self.image_preview, 1)
        self.image_row.addWidget(self.image_btn)
        search_outer.addWidget(self.image_row_widget)

        filter_row = QHBoxLayout()
        self.genre_filter_widget = QWidget()
        genre_filter_layout = QHBoxLayout(self.genre_filter_widget)
        genre_filter_layout.setContentsMargins(0, 0, 0, 0)
        genre_filter_layout.setSpacing(8)
        self.genre_toggle = QPushButton("＋  Add genre filter")
        self.genre_toggle.setObjectName("Ghost")
        self.genre_toggle.setMinimumHeight(40)
        self.genre_toggle.setCheckable(True)
        self.genre_toggle.toggled.connect(self.toggle_genre_filter)
        genre_filter_layout.addWidget(self.genre_toggle)
        self.genre_choice = QComboBox()
        self.genre_choice.setObjectName("GenreSelector")
        self.genre_choice.setMinimumHeight(42)
        genre_items = [
            ("🎬  Any genre", "Any genre"),
            ("💥  Action", "Action"), ("🧭  Adventure", "Adventure"),
            ("✨  Animation", "Animation"), ("😂  Comedy", "Comedy"),
            ("🕵  Crime", "Crime"), ("🎥  Documentary", "Documentary"),
            ("🎭  Drama", "Drama"), ("👨‍👩‍👧  Family", "Family"),
            ("🐉  Fantasy", "Fantasy"), ("👻  Horror", "Horror"),
            ("🔎  Mystery", "Mystery"), ("❤️  Romance", "Romance"),
            ("🚀  Science Fiction", "Science Fiction"),
            ("😱  Thriller", "Thriller"), ("⚔  War", "War"),
            ("🤠  Western", "Western"),
        ]
        for visible, value in genre_items:
            self.genre_choice.addItem(visible, value)
        genre_index = self.genre_choice.findData(self.movie_genre)
        self.genre_choice.setCurrentIndex(genre_index if genre_index >= 0 else 0)
        self.genre_choice.setToolTip(
            "Genre keywords are applied to actor and normal text searches."
        )
        genre_filter_layout.addWidget(self.genre_choice, 0)
        self.genre_choice.setVisible(False)
        filter_row.addWidget(self.genre_filter_widget, 0)
        filter_row.addStretch(1)
        self.search_btn = QPushButton("⌕   Find thumbnails")
        self.search_btn.setObjectName("PrimarySearch")
        self.search_btn.setMinimumHeight(46)
        self.search_btn.setMinimumWidth(190)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.clicked.connect(self.start_search)
        filter_row.addWidget(self.search_btn)
        self.filter_row_widget = QWidget()
        self.filter_row_widget.setLayout(filter_row)
        search_outer.addWidget(self.filter_row_widget)
        root.addWidget(search_panel)

        # Results header
        self.results_header_widget = QWidget()
        results_bar = QHBoxLayout(self.results_header_widget)
        results_bar.setContentsMargins(0, 0, 0, 0)
        results_col = QVBoxLayout()
        results_col.setSpacing(2)
        results_title = QLabel("Explore thumbnails")
        results_title.setObjectName("SectionHeading")
        self.result_label = QLabel("")
        self.result_label.setObjectName("Muted")
        self.result_label.setWordWrap(True)
        results_col.addWidget(results_title)
        results_col.addWidget(self.result_label)
        results_bar.addLayout(results_col, 1)
        self.download_all_btn = QPushButton("↓  Download all shown")
        self.download_all_btn.setObjectName("ToolbarButton")
        self.download_all_btn.setEnabled(False)
        self.download_all_btn.clicked.connect(self.download_all)
        results_bar.addWidget(self.download_all_btn, 0, Qt.AlignVCenter)
        root.addWidget(self.results_header_widget)

        # Search status
        status_panel = QFrame()
        status_panel.setObjectName("StatusPanel")
        status_l = QHBoxLayout(status_panel)
        status_l.setContentsMargins(14, 9, 14, 9)
        self.status = QLabel("Ready")
        self.status.setObjectName("Muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(145)
        self.progress.hide()
        self._loading_dots = 0
        self.loading_timer = QTimer(self)
        self.loading_timer.setInterval(360)
        self.loading_timer.timeout.connect(self._animate_loading_status)
        status_l.addWidget(self.status, 1)
        status_l.addWidget(self.progress)
        self.status_panel = status_panel
        root.addWidget(status_panel)

        # Gallery fills remaining space and adapts columns to window width.
        self.scroll = QScrollArea()
        self.scroll.setObjectName("ResultsScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.gallery = QWidget()
        self.gallery.setObjectName("GalleryCanvas")
        self.grid = QGridLayout(self.gallery)
        self.grid.setContentsMargins(2, 2, 8, 8)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.scroll.setWidget(self.gallery)
        self.scroll.verticalScrollBar().valueChanged.connect(self.on_gallery_scroll)
        root.addWidget(self.scroll, 1)

        # Footer
        self.footer_widget = QWidget()
        footer = QHBoxLayout(self.footer_widget)
        footer.setContentsMargins(0, 0, 0, 0)
        footer_text = QLabel("YOUTUBE THUMBNAILS")
        footer_text.setObjectName("FooterLabel")
        footer.addWidget(footer_text)
        footer.addStretch()
        signature = QLabel("Thumb Finder v1.0 - Hemant")
        signature.setObjectName("FooterSignature")
        footer.addWidget(signature)
        root.addWidget(self.footer_widget)

        self._browse_compact = False
        self.mode.setCurrentIndex(1)
        self.update_placeholders()
        self.show_empty_state()

    def _animate_loading_status(self):
        if not self.loading_more:
            self.loading_timer.stop()
            return
        self._loading_dots = (self._loading_dots + 1) % 4
        base = getattr(self, "_loading_base_text", "Searching movies")
        self.status.setText(base + "." * self._loading_dots)

    def set_loading_state(self, active, message="Searching movies"):
        self.loading_more = bool(active)
        if active:
            self._loading_base_text = message.rstrip(".")
            self.progress.show()
            if not self.loading_timer.isActive():
                self.loading_timer.start()
        else:
            self.loading_timer.stop()
            self.progress.hide()

    def show_empty_state(self):
        self.empty_state = QFrame()
        self.empty_state.setObjectName("Panel")
        self.empty_state.setMinimumHeight(250)
        box = QVBoxLayout(self.empty_state)
        box.setAlignment(Qt.AlignCenter)
        icon = QLabel("▧")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:34pt;color:#8175eb;background:transparent;")
        title = QLabel("Find movie thumbnails")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:15pt;font-weight:800;background:transparent;")
        box.addWidget(icon)
        box.addWidget(title)
        self.grid.addWidget(self.empty_state, 0, 0, 1, 4)

    def toggle_genre_filter(self, checked):
        self.genre_choice.setVisible(bool(checked))
        self.genre_toggle.setText("−  Hide genre filter" if checked else "＋  Add genre filter")

    def update_placeholders(self):
        idx = self.mode.currentIndex()
        self.search_input.setVisible(idx == 0)
        self.image_row_widget.setVisible(idx == 1)
        self.genre_filter_widget.setVisible(idx == 0 and not getattr(self, "_browse_compact", False))
        self.mode_hint.setText(
            "Enter an actor, movie or topic — search intent is detected automatically."
            if idx == 0 else
            "Choose a thumbnail photo to find visually similar results and infer its broad visual category."
        )
        if hasattr(self, "search_btn"):
            self.search_btn.setText("⌕   Search thumbnails" if idx == 0 else "▧   Find similar thumbnails")

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

    @staticmethod
    def resolve_system_dark():
        try:
            scheme = QApplication.instance().styleHints().colorScheme()
            return scheme == Qt.ColorScheme.Dark
        except Exception:
            # Safe fallback when the platform does not expose a color scheme.
            return False

    def apply_theme(self, animate=False):
        app = QApplication.instance()
        app.setStyleSheet(DARK if self.dark else LIGHT)
        if hasattr(self, "theme_btn"):
            self.update_theme_button()
        if animate and hasattr(self, "centralWidget") and self.centralWidget():
            effect = QGraphicsOpacityEffect(self.centralWidget())
            self.centralWidget().setGraphicsEffect(effect)
            effect.setOpacity(0.72)
            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(180)
            animation.setStartValue(0.72)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            animation.finished.connect(lambda: self.centralWidget().setGraphicsEffect(None))
            self._theme_animation = animation
            animation.start()

    def update_theme_button(self):
        if hasattr(self, "theme_btn"):
            self.theme_btn.setText("☀" if self.dark else "☾")
            self.theme_btn.setToolTip("Switch to light mode" if self.dark else "Switch to dark mode")
            self.theme_btn.setFixedSize(44, 44)

    def toggle_theme(self):
        self.dark = not self.dark
        if hasattr(self, "theme_btn"):
            effect = self.theme_btn.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(self.theme_btn)
                self.theme_btn.setGraphicsEffect(effect)
            fade_out = QPropertyAnimation(effect, b"opacity", self)
            fade_out.setDuration(120)
            fade_out.setStartValue(1.0)
            fade_out.setEndValue(0.15)
            fade_out.setEasingCurve(QEasingCurve.OutCubic)
            def swap_theme_icon():
                self.apply_theme(animate=False)
                fade_in = QPropertyAnimation(effect, b"opacity", self)
                fade_in.setDuration(220)
                fade_in.setStartValue(0.15)
                fade_in.setEndValue(1.0)
                fade_in.setEasingCurve(QEasingCurve.OutBack)
                fade_in.finished.connect(lambda: self.theme_btn.setGraphicsEffect(None))
                self._theme_icon_animation = fade_in
                fade_in.start()
            fade_out.finished.connect(swap_theme_icon)
            self._theme_icon_animation = fade_out
            fade_out.start()
        else:
            self.apply_theme(animate=False)
        self.theme_preference = "dark" if self.dark else "light"
        self.config["theme"] = self.theme_preference
        self.config.pop("dark", None)
        if not save_config(self.config):
            self.status.setText("Theme changed for this session, but the preference could not be saved.")

    def open_settings(self):
        try:
            d = SettingsDialog(self, self.download_dir)
            if d.exec():
                selected = d.download_path.text().strip()
                if not selected:
                    raise ValueError("Choose a valid download folder.")
                self.download_dir = Path(selected).expanduser()
                self.download_dir.mkdir(parents=True, exist_ok=True)
                self.config["download_dir"] = str(self.download_dir)
                if save_config(self.config):
                    self.status.setText("Settings saved locally.")
                else:
                    self.status.setText("Settings could not be saved; check folder permissions.")
        except Exception as exc:
            logging.exception("Settings dialog failed")
            QMessageBox.warning(self, "Settings error", str(exc))

    def selected_min_minutes(self):
        return 40

    @staticmethod
    def classify_search_text(text):
        """Lightweight local intent hint; YouTube results remain the source of truth."""
        value = " ".join(text.strip().split())
        low = value.casefold()
        topic_terms = {
            "action", "adventure", "comedy", "horror", "thriller", "romance",
            "sci-fi", "science fiction", "space", "haunted", "survival",
            "explained", "review", "edit", "scene", "scenes", "wallpaper",
            "animation", "cartoon", "gaming", "nature", "travel", "tutorial",
            "compilation", "best", "top"
        }
        if any(term in low for term in topic_terms):
            return "topic"
        words = value.split()
        known_single_names = {"salman", "aamir", "akshay", "hrithik", "deepika",
                              "ranbir", "ranveer", "prabhas", "vijay", "ajith",
                              "rajini", "kamal", "mohanlal", "mammootty",
                              "tom", "brad", "leonardo", "dwayne", "jackie"}
        if len(words) == 1 and low in known_single_names:
            return "actor"
        # Multi-word proper-name-like phrases are treated as actor/person searches.
        if 2 <= len(words) <= 4 and all(w[:1].isupper() for w in words if w):
            return "actor"
        return "topic"

    def make_query(self):
        if self.mode.currentIndex() == 0:
            query = self.search_input.text().strip()
            if not query:
                raise ValueError("Enter an actor name, movie title or topic.")
            intent = self.classify_search_text(query)
            self.detected_search_intent = intent
            if intent == "actor":
                return f"{query} movies", ""
            return f"{query} movie", ""
        if not self.actor_image_path:
            raise ValueError("Choose a reference thumbnail photo first.")
        return "", self.actor_image_path

    def start_search(self):
        self.set_browse_compact(False)
        self.scroll.verticalScrollBar().setValue(0)
        try:
            query, image_path = self.make_query()
        except ValueError as e:
            QMessageBox.warning(self, "Missing search input", str(e))
            return
        if not self.api_key and not self.prompt_for_api_key():
            return
        self.last_query = query
        self.search_image_path = image_path
        self.search_folder_name = query or ("similar_thumbnails_" + Path(image_path).stem)
        self.min_duration_minutes = 40
        self.movie_genre = (
            (self.genre_choice.currentData() or "Any genre")
            if self.mode.currentIndex() == 0 and self.genre_toggle.isChecked() else "Any genre"
        )
        self.config.pop("min_duration_minutes", None)
        self.config["movie_genre"] = self.movie_genre
        self.config.pop("search_language", None)
        self.config.pop("search_region", None)
        if not save_config(self.config):
            self.status.setText("Search preferences could not be saved; continuing with current selections.")
        self.next_token = ""; self.seen_ids.clear(); self.pending_items=[]; self.current_batch=[]
        self.loading_more = False; self.has_more_pages = False
        self.clear_gallery()
        self._visible_cards = []
        self.run_search("")

    def search_single_video(self, video_id):
        self.loading_more = True
        self.search_btn.setEnabled(False)
        self.set_loading_state(True, "Fetching video thumbnail")
        if not hasattr(self, "_video_bridge"):
            from PySide6.QtCore import QObject, Signal
            class Bridge(QObject):
                done = Signal(object, object)
            self._video_bridge = Bridge(self)
            self._video_bridge.done.connect(self._single_video_finished)
        threading.Thread(target=lambda: self._video_bridge.done.emit(*self._fetch_video(video_id)), daemon=True).start()

    def _fetch_video(self, video_id):
        try:
            response = requests.get("https://www.googleapis.com/youtube/v3/videos",
                params={"part":"snippet,statistics,contentDetails","id":video_id,"key":self.api_key}, timeout=(5,20))
            response.raise_for_status()
            items=response.json().get("items", [])
            if not items: raise ValueError("YouTube video was not found or is unavailable.")
            item=items[0]; sn=item.get("snippet",{}); thumbs=sn.get("thumbnails",{})
            quality=next((k for k in ("maxres","standard","high","medium","default") if thumbs.get(k,{}).get("url")),"default")
            stats=item.get("statistics",{})
            return ({"id":video_id,"title":sn.get("title","Untitled"),"channel":sn.get("channelTitle",""),
                "published":sn.get("publishedAt","")[:10],"views":int(stats.get("viewCount",0)),
                "thumbnail":thumbs.get(quality,{}).get("url",""),"thumbnail_quality":quality,
                "duration":parse_youtube_duration(item.get("contentDetails",{}).get("duration","")),
                "video_url":"https://www.youtube.com/watch?v="+video_id}, None)
        except Exception as exc:
            return None, str(exc)

    def _single_video_finished(self, item, error):
        self.set_loading_state(False); self.loading_more=False; self.search_btn.setEnabled(True)
        if error:
            self.status.setText("Could not load video")
            QMessageBox.warning(self, "Video link", error); return
        self.clear_gallery(); self._visible_cards=[]; self.add_cards([item])
        self.seen_ids={item["id"]}; self.result_label.setText("Video thumbnail")
        self.status.setText("Thumbnail ready"); self.download_all_btn.setEnabled(True); self.has_more_pages=False

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
        try:
            self.loading_more = True
            self.search_btn.setEnabled(False)
            self.set_loading_state(True, "Searching YouTube thumbnails…")
            worker = SearchWorker(
                self.api_key, self.last_query, token, BATCH_SIZE,
                self.min_duration_minutes, self.search_image_path, self.movie_genre
            )
            self.search_workers.append(worker)
            worker.signals.finished.connect(
                lambda data, error, w=worker: self._search_worker_finished(w, data, error))
            worker.signals.progress.connect(self.status.setText)
            self.pool.start(worker)
        except Exception as exc:
            self.loading_more = False
            self.set_loading_state(False)
            self.search_btn.setEnabled(True)
            logging.exception("Could not start movie search")
            QMessageBox.critical(self, "Search could not start", str(exc))

    def _search_worker_finished(self, worker, data, error):
        if worker in self.search_workers:
            self.search_workers.remove(worker)
        self.search_finished(data, error)

    def search_finished(self, data, error):
        self.set_loading_state(False)
        self.search_btn.setEnabled(True)
        self.loading_more = False
        if error:
            self.has_more_pages = False
            self.status.setText("Search failed.")
            QMessageBox.critical(self,"YouTube search error",error+"\n\nCheck your internet connection and YouTube API configuration/quota.")
            return
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            logging.error("Search worker returned an invalid response: %r", data)
            self.status.setText("Search returned an invalid response. Please try again.")
            QMessageBox.warning(self, "Search error", "The search returned an unexpected response. See the diagnostic log.")
            return
        known = self.seen_ids | {x["id"] for x in self.pending_items}
        self.pending_items.extend(x for x in data["items"] if x.get("id") and x["id"] not in known)
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
                     ("actor-related movies" if getattr(self, "detected_search_intent", "topic") == "actor" else "movie/topic results"))
        self.result_label.setText(f"{len(self.seen_ids)} {mode_name} found  ·  popular movies first")
        self.status.setText(f"Showing {len(fresh)} popular movies ({self.min_duration_minutes} min+). Scroll for more.")
        self.download_all_btn.setEnabled(bool(self.seen_ids))
        self.has_more_pages = bool(self.pending_items or self.next_token)
        if not fresh and self.next_token:
            self.run_search(self.next_token)
        elif not fresh and not self.seen_ids:
            self.status.setText("No matching videos found. Try another search, genre or a shorter minimum duration.")
            self.result_label.setText("No matching videos found")
            empty = QFrame(); empty.setObjectName("Panel")
            box = QVBoxLayout(empty); box.setAlignment(Qt.AlignCenter)
            title = QLabel("No thumbnails found this time")
            title.setStyleSheet("font-size:14pt;font-weight:800;background:transparent;")
            detail = QLabel("Try another actor, topic, genre or reference image.")
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
        self.result_label.setText("Finding matching thumbnails…")
        self.download_all_btn.setEnabled(False)

    def add_cards(self, items):
        self._visible_cards = getattr(self, "_visible_cards", [])
        new_cards = [ThumbCard(item, self) for item in items]
        self._visible_cards.extend(new_cards)
        for card in new_cards:
            effect = QGraphicsOpacityEffect(card); card.setGraphicsEffect(effect); effect.setOpacity(0.0)
            anim = QPropertyAnimation(effect, b"opacity", card); anim.setDuration(300)
            anim.setStartValue(0.0); anim.setEndValue(1.0); anim.setEasingCurve(QEasingCurve.OutQuart)
            card._entry_animation = anim; anim.start()
        self.reflow_gallery(); self.current_batch = items

    def reflow_gallery(self):
        cards = getattr(self, "_visible_cards", [])
        if not cards:
            return
        while self.grid.count():
            item = self.grid.takeAt(0)
            # Keep the widgets alive while moving them to their new positions.
        width = max(260, self.scroll.viewport().width())
        columns = max(1, min(4, width // 285))
        for col in range(4):
            self.grid.setColumnStretch(col, 1 if col < columns else 0)
        for i, card in enumerate(cards):
            self.grid.addWidget(card, i // columns, i % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "centralWidget") and self.centralWidget():
            compact = self.width() < 850
            margins = (14, 12, 14, 12) if compact else (24, 20, 24, 18)
            layout = self.centralWidget().layout()
            if layout:
                layout.setContentsMargins(*margins)
                layout.setSpacing(12 if compact else 18)
            if hasattr(self, "search_btn"):
                self.search_btn.setMinimumWidth(150 if compact else 190)
        if hasattr(self, "_visible_cards"):
            self.reflow_gallery()

    def open_thumbnail_editor(self, item):
        """Download the selected thumbnail locally, then open the non-destructive editor."""
        try:
            from .editor import ThumbnailEditor
            response = requests.get(item.get("thumbnail", ""), timeout=(5, 25))
            response.raise_for_status()
            from PIL import Image
            from io import BytesIO
            handle = tempfile.NamedTemporaryFile(prefix="thumb_finder_edit_", suffix=".jpg", delete=False)
            temp_path = Path(handle.name)
            handle.close()
            with Image.open(BytesIO(response.content)) as source:
                source.convert("RGB").save(temp_path, format="JPEG", quality=95)
            dialog = ThumbnailEditor(temp_path, self)
            dialog.exec()
        except Exception as exc:
            logging.exception("Could not open thumbnail editor")
            QMessageBox.warning(self, "Editor unavailable", f"Could not download or open this thumbnail.\n\n{exc}")

    def download_item(self, item):
        self.start_download([item])
    def download_all(self):
        items=[card.item for card in getattr(self, "_visible_cards", [])]
        if items: self.start_download(items)
    def start_download(self, items):
        try:
            folder = self.download_dir / self.safe_name(
                self.search_folder_name or self.last_query or "similar_thumbnails")
            worker = DownloadWorker(items, folder)
            self.download_workers.append(worker)
            worker.signals.done.connect(self.download_finished)
            worker.signals.done.connect(
                lambda _a, _b, w=worker: self.download_workers.remove(w)
                if w in self.download_workers else None)
            self.status.setText("Downloading thumbnails in background…")
            self.pool.start(worker)
        except Exception as exc:
            logging.exception("Could not start thumbnail download")
            QMessageBox.warning(self, "Download error", str(exc))
    def download_finished(self, message, error):
        self.status.setText(message)
        if error:
            QMessageBox.warning(self, "Download failed", error)
        else:
            folder = self.download_dir / self.safe_name(
                self.search_folder_name or self.last_query or "similar_thumbnails")
            QMessageBox.information(self, "Download complete", f"{message}\nSaved to:\n{folder}")

    def set_browse_compact(self, compact):
        """Collapse the search area into a slim expandable bar while browsing."""
        compact = bool(compact)
        if compact == getattr(self, "_browse_compact", False):
            return
        self._browse_compact = compact
        self.top_widget.setVisible(not compact)
        self.hero_widget.setVisible(False)
        self.results_header_widget.setVisible(not compact)
        self.status_panel.setVisible(not compact)
        self.footer_widget.setVisible(not compact)
        self.search_top_widget.setVisible(not compact)
        self.compact_search_btn.setVisible(compact)
        self.mode.setVisible(not compact)
        self.search_input.setVisible(not compact and self.mode.currentIndex() == 0)
        self.image_row_widget.setVisible(not compact and self.mode.currentIndex() == 1)
        self.filter_row_widget.setVisible(not compact)
        # Language/region controls were removed; older layouts may not define this row.
        locale_row = getattr(self, "locale_row_widget", None)
        if locale_row is not None:
            locale_row.setVisible(not compact)
        self.genre_filter_widget.setVisible(not compact and self.mode.currentIndex() == 0)
        margins = (8, 5, 8, 5) if compact else ((14, 12, 14, 12) if self.width() < 850 else (24, 20, 24, 18))
        central_layout = self.centralWidget().layout()
        central_layout.setContentsMargins(*margins)
        central_layout.setSpacing(5 if compact else (12 if self.width() < 850 else 18))
        if hasattr(self, "search_panel_layout"):
            self.search_panel_layout.setContentsMargins(10, 5, 10, 5) if compact else self.search_panel_layout.setContentsMargins(20, 18, 20, 18)
            self.search_panel_layout.setSpacing(5 if compact else 13)
        # Animate the compact search panel height for a smooth collapse/expand.
        panel = self.search_panel
        if hasattr(self, "_search_panel_anim") and self._search_panel_anim:
            self._search_panel_anim.stop()
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve
        target = 54 if compact else panel.sizeHint().height()
        panel.setMaximumHeight(16777215 if not compact else max(panel.height(), target))
        anim = QPropertyAnimation(panel, b"maximumHeight", self)
        anim.setDuration(280)
        anim.setStartValue(panel.height())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutQuart)
        if not compact:
            anim.finished.connect(lambda: panel.setMaximumHeight(16777215))
        self._search_panel_anim = anim
        anim.start()

    def on_gallery_scroll(self, value):
        # Collapse surrounding chrome with a short height animation and preserve scroll position.
        was_compact = getattr(self, "_browse_compact", False)
        should_compact = value > 35
        if should_compact != was_compact:
            bar = self.scroll.verticalScrollBar()
            self.set_browse_compact(should_compact)
            bar.setValue(min(value, bar.maximum()))
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


def main():
    log_path = configure_logging()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    sys.excepthook = handle_unhandled_exception

    # Check the remote live switch and minimum supported version before creating
    # the main window. A network failure is fail-open inside release_control.py.
    release_state = evaluate_release(fetch_release_control(), APP_VERSION)
    if not release_state["allowed"]:
        message = release_state["message"] or (
            "Thumb Finder is temporarily unavailable." if not release_state["enabled"]
            else f"Please update Thumb Finder to version {release_state['minimum_version']} or newer."
        )
        QMessageBox.warning(None, "Thumb Finder unavailable", message)
        if release_state["enabled"]:
            QDesktopServices.openUrl(QUrl(release_state["release_url"]))
        return 0
    if release_state["update_available"]:
        latest = release_state["latest_version"]
        message = release_state["message"] or f"Thumb Finder {latest} is available."
        answer = QMessageBox.question(
            None, "Update available",
            f"{message}\n\nInstalled version: {APP_VERSION}\nLatest version: {latest}\n\nOpen the download page?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if answer == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(release_state["release_url"]))

    def thread_exception_hook(args):
        logging.critical("Unhandled background-thread exception",
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    if hasattr(threading, "excepthook"):
        threading.excepthook = thread_exception_hook

    resource_root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    icon_path = resource_root / ("app_icon.ico" if sys.platform == "win32" else "app_icon.icns")
    if not icon_path.exists():
        icon_path = Path(__file__).parent / "app_icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    try:
        window = MainWindow()
        if not window.run_first_launch_setup():
            return 1
        window.show()
        logging.info("Thumb Finder %s started in local-debug mode", APP_VERSION)
        # Delay the first-run prompt until Qt has painted the main window.
        if not window.api_key:
            QTimer.singleShot(120, window.prompt_for_api_key)
        return app.exec()
    except Exception as exc:
        logging.exception("Fatal startup error")
        QMessageBox.critical(
            None,
            "Thumb Finder could not start",
            f"The application encountered a startup error.\n\n{exc}\n\n"
            f"Diagnostic log: {log_path or 'Unavailable'}",
        )
        return 1

if __name__ == "__main__":
    main()
