"""Non-destructive thumbnail editor with resizable rectangle selection and local inpainting."""
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QPoint, QThread, Signal
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QImage
from PySide6.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QSlider, QFileDialog, QMessageBox, QFormLayout, QProgressDialog, QButtonGroup,
    QScrollArea, QFrame
)


def _qimage_to_rgb_array(image):
    """Convert a detached QImage to RGB bytes; call from a worker thread."""
    import numpy as np
    image = image.convertToFormat(QImage.Format_RGB888)
    width, height, stride = image.width(), image.height(), image.bytesPerLine()
    raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
    return raw.reshape(height, stride)[:, :width * 3].reshape(height, width, 3).copy()


def _compatible_ai_python(root: Path):
    """Return a Python 3.11 interpreter for legacy AI packages.

    Python 3.14 is fine for the main app, but PyTorch/LaMa/Real-ESRGAN's
    dependency stack is not consistently published for it. On Windows we
    bootstrap a private per-user Python 3.11 install; it does not replace the
    user's Python or affect the main app environment.
    """
    import os, platform, shutil, subprocess, sys, urllib.request
    if sys.version_info[:2] == (3, 11):
        return Path(sys.executable)
    if platform.system() == "Windows":
        base = root / "AI-Python311"
        python = base / "python.exe"
        if python.exists():
            return python
        base.parent.mkdir(parents=True, exist_ok=True)
        installer = root / "python-3.11.9-amd64.exe"
        if not installer.exists():
            url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
            request = urllib.request.Request(url, headers={"User-Agent": "ThumbFinder/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response, open(installer, "wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk: break
                    out.write(chunk)
        result = subprocess.run([str(installer), "/quiet", "InstallAllUsers=0",
                                 f"TargetDir={base}", "Include_pip=1", "Include_launcher=0",
                                 "Include_test=0", "PrependPath=0", "Shortcuts=0"],
                                capture_output=True, text=True, timeout=600)
        if not python.exists():
            raise RuntimeError("Could not prepare the private Python 3.11 AI runtime. "
                               "Check internet access and Windows permissions.\n" +
                               (result.stderr or result.stdout)[-2000:])
        return python
    # macOS/Linux: prefer an already-installed compatible interpreter.
    candidates = [shutil.which("python3.11"), shutil.which("python3.12"), shutil.which("python3.10")]
    for candidate in candidates:
        if candidate:
            check = subprocess.run([candidate, "-c", "import sys; print(sys.version_info[:2])"],
                                   capture_output=True, text=True)
            if check.returncode == 0:
                return Path(candidate)
    if sys.version_info < (3, 13):
        return Path(sys.executable)
    raise RuntimeError("LaMa and Real-ESRGAN need a compatible Python 3.10–3.12 runtime. "
                       "Install Python 3.11 or 3.12 and retry.")


def _removal_assets_ready():
    """Fast filesystem-only check; runtime imports are deliberately done in the worker."""
    import os, platform
    if platform.system() == "Windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ThumbFinder"
        runtime = root / f"lama-runtime-py311-{platform.machine().lower()}"
        python = runtime / "Scripts" / "python.exe"
    else:
        root = Path.home() / "Library" / "Application Support" / "ThumbFinder"
        runtime = root / f"lama-runtime-py311-{platform.machine().lower()}"
        python = runtime / "bin" / "python"
    hf = root / "Models" / "huggingface" / "hub"
    torch_cache = root / "Models" / "torch"
    has_sam = hf.exists() and any(hf.glob("models--facebook--sam2.1-hiera-*"))
    has_lama = torch_cache.exists() and any(torch_cache.iterdir())
    return bool(python.exists() and has_sam and has_lama)


def _enhance_assets_ready():
    """Fast filesystem-only check; package import validation runs in EnhanceThread."""
    try:
        import os
        runtime, model = EnhanceThread.paths()
        python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return python.exists() and model.exists() and model.stat().st_size >= 10_000_000
    except Exception:
        return False


class SelectionPreview(QLabel):
    selectionChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(560, 315)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self._pixmap = QPixmap()
        self._start = self._end = None
        self.selection = None                 # rectangle in widget coordinates
        self._drag_mode = None
        self._drag_origin = None
        self._original_rect = None
        self._handle_size = 9
        self.setStyleSheet("background:#171923;border:1px solid #383b4b;border-radius:10px;")

    def set_image(self, pixmap):
        self._pixmap = pixmap
        self._start = self._end = self.selection = None
        self._drag_mode = None
        self.selectionChanged.emit(None)
        self.update()

    def image_rect(self):
        if self._pixmap.isNull():
            return QRect()
        area = self.contentsRect()
        scaled = self._pixmap.size().scaled(area.size(), Qt.KeepAspectRatio)
        return QRect(area.x() + (area.width()-scaled.width())//2,
                     area.y() + (area.height()-scaled.height())//2,
                     scaled.width(), scaled.height())

    def _clamp(self, point):
        target = self.image_rect()
        if target.isNull():
            return point
        return QPoint(min(max(point.x(), target.left()), target.right()),
                      min(max(point.y(), target.top()), target.bottom()))

    def _handles(self, rect):
        s = self._handle_size
        cx, cy = rect.center().x(), rect.center().y()
        return {
            "tl": QPoint(rect.left(), rect.top()), "tm": QPoint(cx, rect.top()),
            "tr": QPoint(rect.right(), rect.top()), "mr": QPoint(rect.right(), cy),
            "br": QPoint(rect.right(), rect.bottom()), "bm": QPoint(cx, rect.bottom()),
            "bl": QPoint(rect.left(), rect.bottom()), "ml": QPoint(rect.left(), cy),
        }

    def _hit_handle(self, point):
        if not self.selection:
            return None
        for name, pos in self._handles(self.selection).items():
            if abs(point.x()-pos.x()) <= self._handle_size and abs(point.y()-pos.y()) <= self._handle_size:
                return name
        return None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._pixmap.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        target = self.image_rect()
        p.drawPixmap(target, self._pixmap)
        rect = self.selection
        if self._start is not None and self._end is not None:
            rect = QRect(self._start, self._end).normalized()
        if rect:
            p.setPen(QPen(QColor(255, 205, 65), 2, Qt.SolidLine))
            p.fillRect(rect, QColor(255, 205, 65, 28))
            p.drawRect(rect)
            p.setPen(QPen(QColor(25, 27, 39), 1))
            p.setBrush(QColor(255, 220, 120))
            for pos in self._handles(rect).values():
                p.drawRect(pos.x()-4, pos.y()-4, 8, 8)
        p.end()

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        if event.button() == Qt.LeftButton and self.image_rect().contains(point):
            handle = self._hit_handle(point)
            if handle:
                self._drag_mode = handle
                self._original_rect = QRect(self.selection)
                self._drag_origin = point
            elif self.selection and self.selection.adjusted(-4, -4, 4, 4).contains(point):
                self._drag_mode = "move"
                self._original_rect = QRect(self.selection)
                self._drag_origin = point
            else:
                self._drag_mode = "new"
                self._start = self._end = point
                self.selection = None
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        point = self._clamp(event.position().toPoint())
        if self._drag_mode == "new":
            self._end = point
            self.update()
            event.accept(); return
        if self._drag_mode and self._original_rect:
            old = self._original_rect
            dx, dy = point.x()-self._drag_origin.x(), point.y()-self._drag_origin.y()
            if self._drag_mode == "move":
                r = QRect(old).translated(dx, dy)
                target = self.image_rect()
                if r.left() < target.left(): r.moveLeft(target.left())
                if r.top() < target.top(): r.moveTop(target.top())
                if r.right() > target.right(): r.moveRight(target.right())
                if r.bottom() > target.bottom(): r.moveBottom(target.bottom())
            else:
                left, top, right, bottom = old.left(), old.top(), old.right(), old.bottom()
                if "l" in self._drag_mode: left = min(point.x(), right-4)
                if "r" in self._drag_mode: right = max(point.x(), left+4)
                if "t" in self._drag_mode: top = min(point.y(), bottom-4)
                if "b" in self._drag_mode: bottom = max(point.y(), top+4)
                r = QRect(QPoint(left, top), QPoint(right, bottom)).normalized().intersected(self.image_rect())
            self.selection = r
            self.update(); event.accept(); return
        if self.selection and self._hit_handle(point):
            self.setCursor(Qt.SizeFDiagCursor)
        elif self.selection and self.selection.adjusted(-4,-4,4,4).contains(point):
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.CrossCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_mode:
            if self._drag_mode == "new" and self._start is not None and self._end is not None:
                r = QRect(self._start, self._end).normalized().intersected(self.image_rect())
                self.selection = r if r.width() >= 5 and r.height() >= 5 else None
            self._start = self._end = None
            self._drag_mode = None
            self._original_rect = self._drag_origin = None
            self.selectionChanged.emit(self.selection_in_image())
            self.update(); event.accept(); return
        super().mouseReleaseEvent(event)

    def selection_in_image(self):
        if not self.selection or self._pixmap.isNull():
            return None
        target = self.image_rect()
        r = self.selection.intersected(target)
        if target.isNull() or r.width() < 5 or r.height() < 5:
            return None
        sx = self._pixmap.width() / float(target.width())
        sy = self._pixmap.height() / float(target.height())
        x0 = max(0, min(self._pixmap.width()-1, round((r.left()-target.left())*sx)))
        y0 = max(0, min(self._pixmap.height()-1, round((r.top()-target.top())*sy)))
        x1 = max(x0+1, min(self._pixmap.width(), round((r.right()-target.left()+1)*sx)))
        y1 = max(y0+1, min(self._pixmap.height(), round((r.bottom()-target.top()+1)*sy)))
        return (x0, y0, x1-x0, y1-y0)


class InpaintThread(QThread):
    """SAM 2.1 object selection + Big-LaMa inpainting in a persistent local worker."""
    finished_image = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    _worker_process = None
    _worker_lock = __import__("threading").Lock()

    def __init__(self, rgb, box, parent=None):
        super().__init__(parent)
        self.rgb, self.box = rgb, box

    @staticmethod
    def _paths():
        import os, platform, sys
        system = platform.system()
        if system == "Windows":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "ThumbFinder"
        elif system == "Darwin":
            root = Path.home() / "Library" / "Application Support" / "ThumbFinder"
        else:
            root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ThumbFinder"
        runtime_name = f"lama-runtime-py311-{platform.machine().lower()}"
        return root, root / runtime_name

    def _ensure_runtime(self, runtime_dir):
        import subprocess, sys, platform
        python = runtime_dir / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
        if not python.exists():
            self.status.emit("Setting up the private AI runtime…")
            runtime_dir.parent.mkdir(parents=True, exist_ok=True)
            base_python = _compatible_ai_python(runtime_dir.parent)
            result = subprocess.run([str(base_python), "-m", "venv", str(runtime_dir)], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError("Could not create the object-removal AI environment.\n" + (result.stderr or result.stdout)[-2500:])
        check = subprocess.run([str(python), "-c", "import torch, torchvision; import simple_lama_inpainting; from transformers import Sam2Model, Sam2Processor"], capture_output=True, text=True)
        if check.returncode:
            self.status.emit("Installing AI libraries: PyTorch, SAM 2.1 and LaMa…")
            packages = [
                "torch==2.5.1", "torchvision==0.20.1", "simple-lama-inpainting==0.1.2",
                "fire==0.5.0", "transformers==5.2.0", "safetensors", "accelerate",
                "Pillow", "numpy<2", "opencv-python-headless>=4.10,<5",
            ]
            result = subprocess.run([str(python), "-m", "pip", "install", "--upgrade", *packages], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(
                    "Could not install the prebuilt SAM 2.1 + PyTorch + LaMa runtime. "
                    "No compiler is required; check Python compatibility and internet access.\n\n"
                    + (result.stderr or result.stdout)[-4000:]
                )
        return python

    @classmethod
    def _stop_worker(cls):
        process = cls._worker_process
        cls._worker_process = None
        if process and process.poll() is None:
            try:
                process.stdin.write("\n")
                process.stdin.flush()
                process.stdin.close()
                process.wait(timeout=3)
            except Exception:
                try: process.kill()
                except Exception: pass

    def _get_worker(self, python, helper, model_path, root):
        import os, subprocess, sys
        process = self.__class__._worker_process
        if process is not None and process.poll() is None:
            return process
        env = os.environ.copy()
        env["HF_HOME"] = str(root / "Models" / "huggingface")
        env["TORCH_HOME"] = str(root / "Models" / "torch")
        env["PYTHONUNBUFFERED"] = "1"
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = open(log_dir / "lama_worker.log", "a", encoding="utf-8")
        process = subprocess.Popen(
            [str(python), str(helper), "--server"], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=log_file, text=True, encoding="utf-8",
            bufsize=1, env=env,
        )
        self.__class__._worker_process = process
        import atexit
        atexit.register(self.__class__._stop_worker)
        return process

    def run(self):
        import json, subprocess, tempfile, threading
        import numpy as np
        from PIL import Image
        try:
            root, runtime_dir = self._paths()
            python = self._ensure_runtime(runtime_dir)
            x, y, w, h = self.box
            rgb = _qimage_to_rgb_array(self.rgb) if isinstance(self.rgb, QImage) else self.rgb
            image = Image.fromarray(rgb.astype(np.uint8), mode="RGB")

            # SAM 2.1 uses the rectangle as a prompt to segment the object itself.
            # The selection is not treated as a rectangular hole.
            with self._worker_lock:
                with tempfile.TemporaryDirectory(prefix="thumbfinder-remove-") as temp:
                    temp = Path(temp)
                    image_path, output_path = temp / "input.png", temp / "output.png"
                    image.save(image_path)
                    helper = Path(__file__).with_name("ai_worker.py")
                    self.status.emit("Starting AI engine…")
                    process = self._get_worker(python, helper, None, root)
                    job = {"image": str(image_path), "output": str(output_path), "box": [x, y, x+w, y+h]}
                    try:
                        process.stdin.write(json.dumps(job) + "\n")
                        process.stdin.flush()
                        while True:
                            response_line = process.stdout.readline()
                            if not response_line:
                                raise RuntimeError("The object-removal worker stopped unexpectedly. Check ThumbFinder\\logs\\lama_worker.log and try again.")
                            event = json.loads(response_line)
                            if "status" in event:
                                self.status.emit(event["status"])
                                continue
                            response = event
                            break
                    except Exception:
                        self._stop_worker()
                        raise
                    if not response.get("ok"):
                        raise RuntimeError(response.get("error", "Object removal failed."))
                    if not output_path.exists():
                        raise RuntimeError("The removal model finished without creating an output image.")
                    processed = Image.open(output_path).convert("RGB")
                    if processed.size != image.size:
                        raise RuntimeError("The removal model returned an image with unexpected dimensions.")
                    self.finished_image.emit(np.asarray(processed, dtype=np.uint8).copy())
        except Exception as exc:
            self.failed.emit(f"Local SAM 2.1 + LaMa object removal failed: {exc}")


class EnhanceThread(QThread):
    """Optional local Real-ESRGAN enhancement; runtime and weights download on demand."""
    finished_image = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, rgb, parent=None):
        super().__init__(parent); self.rgb = rgb

    @staticmethod
    def paths():
        import os, sys, platform
        if sys.platform == "win32":
            support = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        elif sys.platform == "darwin":
            support = Path.home() / "Library" / "Application Support"
        else:
            support = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        app_dir = support / "ThumbFinder"
        runtime_dir = app_dir / f"realesrgan-py311-{platform.machine().lower()}"
        weights_dir = app_dir / "Models"
        model_path = weights_dir / "RealESRGAN_x4plus.pth"
        return runtime_dir, model_path

    def run(self):
        import subprocess, sys, tempfile, os
        try:
            env, model=self.paths()
            py = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not py.exists():
                self.status.emit("Setting up the private enhancement runtime…")
                env.parent.mkdir(parents=True,exist_ok=True)
                base_python=_compatible_ai_python(env.parent)
                r=subprocess.run([str(base_python),"-m","venv",str(env)],capture_output=True,text=True)
                if r.returncode: raise RuntimeError((r.stderr or r.stdout)[-2500:])
            check=subprocess.run([str(py),"-c","import torch, torchvision, sys; sys.modules['torchvision.transforms.functional_tensor']=torchvision.transforms.functional; import realesrgan, basicsr"],capture_output=True,text=True)
            if check.returncode:
                self.status.emit("Installing enhancement libraries: PyTorch and Real-ESRGAN…")
                # Install tensor wheels first, then pin the legacy ESRGAN stack.
                # --no-deps avoids pip selecting mutually incompatible historical
                # basicsr/realesrgan releases; required runtime dependencies follow.
                commands = [
                    [str(py),"-m","pip","install","--upgrade","torch==2.5.1","torchvision==0.20.1","numpy<2"],
                    [str(py),"-m","pip","install","--no-deps","basicsr==1.4.2","realesrgan==0.3.0"],
                    [str(py),"-m","pip","install","addict","future","lmdb","numpy<2","opencv-python","Pillow","PyYAML","requests","scikit-image","scipy","tqdm","yapf","facexlib==0.3.0","gfpgan==1.3.8"],
                ]
                logs=[]
                for command in commands:
                    r=subprocess.run(command,capture_output=True,text=True)
                    if r.returncode:
                        logs.append((r.stderr or r.stdout)[-2500:]); break
                if r.returncode: raise RuntimeError("Pinned Real-ESRGAN runtime installation failed.\n"+"\n".join(logs))
                if r.returncode: raise RuntimeError("No compatible prebuilt AI package set is available for this Python version. The main app is unaffected.\n"+(r.stderr or r.stdout)[-3000:])
            if not model.exists():
                self.status.emit("Downloading Real-ESRGAN x4 model weights…")
                model.parent.mkdir(parents=True, exist_ok=True)
                url="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
                r=subprocess.run([str(py),"-c",f"import urllib.request; urllib.request.urlretrieve({url!r}, {str(model)!r})"],capture_output=True,text=True)
                if r.returncode or not model.exists(): raise RuntimeError("Could not download the enhancement model.\n"+(r.stderr or r.stdout)[-2000:])
            with tempfile.TemporaryDirectory(prefix="thumbfinder-enhance-") as td:
                td=Path(td); inp=td/"input.png"; out=td/"output.png"
                from PIL import Image
                rgb = _qimage_to_rgb_array(self.rgb) if isinstance(self.rgb, QImage) else self.rgb
                Image.fromarray(rgb).save(inp)
                helper=Path(__file__).with_name("enhance_worker.py")
                self.status.emit("Running Real-ESRGAN: analysing details and upscaling…")
                r=subprocess.run([str(py),str(helper),"--input",str(inp),"--output",str(out),"--model",str(model)],capture_output=True,text=True,timeout=1800)
                if r.returncode or not out.exists(): raise RuntimeError((r.stderr or r.stdout)[-3000:])
                enhanced=Image.open(out).convert("RGB")
                # Preserve the complete enhanced image. Standard YouTube thumbnails
                # are 16:9 and become exactly 1920x1080; other aspect ratios are
                # scaled to fit the same canvas without silently cropping content.
                from PIL import ImageOps
                enhanced=ImageOps.contain(enhanced, (1920,1080), Image.Resampling.LANCZOS)
                canvas=Image.new("RGB", (1920,1080), (18,20,28))
                canvas.paste(enhanced, ((1920-enhanced.width)//2, (1080-enhanced.height)//2))
                enhanced=canvas
                import numpy as np
                self.finished_image.emit(np.asarray(enhanced,dtype=np.uint8).copy())
        except Exception as exc: self.failed.emit(str(exc))


class ThumbnailEditor(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit thumbnail")
        self.resize(1100, 790)
        self.setMinimumSize(480, 500)
        self.image_path = Path(image_path)
        self.original = QImage(str(self.image_path)).convertToFormat(QImage.Format_RGB888)
        if self.original.isNull():
            raise ValueError("Could not open the downloaded thumbnail.")
        self.current = self.original.copy()
        self.tone_base = self.current.copy()
        self.history = []
        self.redo_history = []
        self._showing_before = False
        self._inpaint_thread = None
        root = QVBoxLayout(self)
        heading = QLabel("Thumbnail Editor")
        heading.setStyleSheet("font-size:20px;font-weight:800;")
        root.addWidget(heading)
        top_tools = QHBoxLayout()
        top_tools.addStretch(1)
        self.compare_btn = QPushButton("◐  Compare")
        self.compare_btn.setCheckable(True)
        self.compare_btn.setToolTip("Hold/toggle to compare the original image with your edits")
        self.compare_btn.clicked.connect(self.toggle_comparison)
        top_tools.addWidget(self.compare_btn)
        root.addLayout(top_tools)
        self.selection_hint = QLabel("Select an area on the image")
        self.selection_hint.setStyleSheet("color:#8b91a5;font-size:12px;font-weight:600;")
        root.addWidget(self.selection_hint)
        self.feature_bar = QHBoxLayout()
        self.feature_bar.setSpacing(8)
        self.remove_btn = QPushButton("Remove Objects")
        self.auto_btn = QPushButton("Auto Adjust")
        self.enhance_btn = QPushButton("✦  HD Enhance")
        self.enhance_btn.setToolTip("Enhance thumbnail details and export at 1920 × 1080")
        for button in (self.remove_btn, self.auto_btn, self.enhance_btn):
            button.setMinimumHeight(42); self.feature_bar.addWidget(button)
        root.addLayout(self.feature_bar)
        self.preview = SelectionPreview()
        self.preview.selectionChanged.connect(self._show_selection_size)
        root.addWidget(self.preview, 1)

        # Canva-style Auto Adjust workspace: one-click correction followed by
        # individual, non-destructive controls with visible numeric values.
        self.auto_adjust_btn = QPushButton("🪄  Auto Adjust")
        self.auto_adjust_btn.setMinimumHeight(44)
        self.auto_adjust_btn.setObjectName("AutoAdjustPrimary")
        self.auto_adjust_btn.setStyleSheet(
            "QPushButton#AutoAdjustPrimary { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #8064f5,stop:1 #e13fa2); color:white; border:0; border-radius:12px; font-weight:800; }"
            "QPushButton#AutoAdjustPrimary:hover { background:#a15fe8; }"
        )
        root.addWidget(self.auto_adjust_btn)

        adjustment_scroll = QScrollArea()
        adjustment_scroll.setWidgetResizable(True)
        adjustment_scroll.setFrameShape(QFrame.NoFrame)
        adjustment_scroll.setMaximumHeight(300)
        adjustment_panel = QWidget()
        adjustment_layout = QVBoxLayout(adjustment_panel)
        adjustment_layout.setContentsMargins(0, 2, 0, 2)
        adjustment_layout.setSpacing(5)
        self.adjustment_sliders = {}
        self.adjustment_values = {}
        slider_specs = [
            ("Brightness", "brightness", -100, 100, 0),
            ("Contrast", "contrast", -100, 100, 0),
            ("Highlights", "highlights", -100, 100, 0),
            ("Shadows", "shadows", -100, 100, 0),
            ("Temperature", "temperature", -100, 100, 0),
            ("Tint", "tint", -100, 100, 0),
            ("Saturation", "saturation", -100, 100, 0),
            ("Vibrance", "vibrance", -100, 100, 0),
            ("Clarity", "clarity", 0, 100, 0),
            ("Sharpness", "sharpness", 0, 100, 0),
        ]
        for label_text, key, low, high, default in slider_specs:
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(1)
            header = QHBoxLayout()
            name_label = QLabel(label_text)
            name_label.setStyleSheet("font-size:12px;font-weight:600;")
            value_label = QLabel(str(default))
            value_label.setMinimumWidth(24)
            value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_label.setStyleSheet("color:#9298ad;font-size:11px;")
            header.addWidget(name_label)
            header.addStretch(1)
            header.addWidget(value_label)
            slider = self._slider(low, high, default)
            slider.setMinimumHeight(16)
            slider.valueChanged.connect(lambda value, target=value_label: target.setText(str(value)))
            slider.valueChanged.connect(self.apply_tone)
            self.adjustment_sliders[key] = slider
            self.adjustment_values[key] = value_label
            row_layout.addLayout(header)
            row_layout.addWidget(slider)
            adjustment_layout.addWidget(row)
        adjustment_scroll.setWidget(adjustment_panel)
        root.addWidget(adjustment_scroll)

        controls = QHBoxLayout()
        history_row = QHBoxLayout()
        self.undo_btn = QPushButton("↶")
        self.undo_btn.setToolTip("Undo (Ctrl+Z)")
        self.undo_btn.setFixedSize(42, 38)
        self.redo_btn = QPushButton("↷")
        self.redo_btn.setToolTip("Redo (Ctrl+Y)")
        self.redo_btn.setFixedSize(42, 38)
        history_row.addWidget(self.undo_btn)
        history_row.addWidget(self.redo_btn)
        controls.addLayout(history_row)
        controls.addStretch(1)
        self.reset_btn = QPushButton("Reset adjustments")
        self.save_btn = QPushButton("Save JPG")
        self.reset_btn.setMinimumHeight(38)
        self.save_btn.setMinimumHeight(38)
        controls.addWidget(self.reset_btn)
        controls.addWidget(self.save_btn)
        root.addLayout(controls)
        self.brightness = self.adjustment_sliders["brightness"]
        self.contrast = self.adjustment_sliders["contrast"]
        self.saturation = self.adjustment_sliders["saturation"]
        self.remove_btn.clicked.connect(self.remove_selection)
        self.auto_btn.clicked.connect(self.auto_adjust)
        self.auto_adjust_btn.clicked.connect(self.auto_adjust)
        self.enhance_btn.clicked.connect(self.enhance_quality)
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)
        self.reset_btn.clicked.connect(self.reset)
        from PySide6.QtGui import QShortcut, QKeySequence
        self._undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self._undo_shortcut.activated.connect(self.undo)
        self._redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self._redo_shortcut.activated.connect(self.redo)
        self.save_btn.clicked.connect(self.save_copy)
        self._refresh()

    def _show_selection_size(self, box):
        if not box:
            self.selection_hint.setText("Drag a rectangle around the object")
        else:
            x, y, w, h = box
            self.selection_hint.setText(f"Selected: {w} × {h} px")

    def _slider(self, low, high, value):
        s = QSlider(Qt.Horizontal); s.setRange(low, high); s.setValue(value); return s

    def _push_history(self):
        self.history.append(self.current.copy())
        self.history = self.history[-30:]
        self.redo_history.clear()
        self._update_history_buttons()

    def _update_history_buttons(self):
        if hasattr(self, "undo_btn"):
            self.undo_btn.setEnabled(bool(self.history))
            self.redo_btn.setEnabled(bool(self.redo_history))

    def _refresh(self):
        shown = self.original if self._showing_before else self.current
        self.preview.set_image(QPixmap.fromImage(shown))
        self._update_history_buttons()

    def toggle_comparison(self, checked=None):
        self._showing_before = self.compare_btn.isChecked()
        self.compare_btn.setText("◐  Showing Original" if self._showing_before else "◐  Compare")
        self._refresh()

    @staticmethod
    def _qimage_to_rgb_array(image):
        import numpy as np
        image = image.convertToFormat(QImage.Format_RGB888)
        width, height, stride = image.width(), image.height(), image.bytesPerLine()
        raw = np.frombuffer(image.constBits(), dtype=np.uint8, count=image.sizeInBytes())
        return raw.reshape(height, stride)[:, :width*3].reshape(height, width, 3).copy()

    def _to_array(self): return self._qimage_to_rgb_array(self.current)

    def _from_array(self, arr):
        import numpy as np
        arr = np.ascontiguousarray(arr.astype(np.uint8))
        return QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format_RGB888).copy()

    def _reset_sliders(self):
        self._tone_slider_baseline = {key: 0 for key in self.adjustment_sliders}
        self._tone_slider_baseline["contrast"] = 0
        for key, slider in self.adjustment_sliders.items():
            slider.blockSignals(True)
            slider.setValue(0)
            slider.blockSignals(False)
            if key in self.adjustment_values:
                self.adjustment_values[key].setText("0")

    def apply_tone(self):
        try:
            import numpy as np
            from PIL import Image, ImageEnhance, ImageFilter
            base = self._qimage_to_rgb_array(self.tone_base).astype(np.float32) / 255.0
            baseline = getattr(self, "_tone_slider_baseline", {})
            value = lambda key: self.adjustment_sliders[key].value() - baseline.get(key, 0)
            # Exposure and contrast
            arr = np.clip(base * max(0.0, 1.0 + value("brightness") / 100.0), 0.0, 1.0)
            contrast = 1.0 + value("contrast") / 100.0
            lum = (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2])[..., None]
            arr = np.clip((arr - lum) * contrast + lum, 0.0, 1.0)
            # Highlights and shadows are weighted by luminance so midtones remain stable.
            lum = (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2])
            hi = np.clip((lum - 0.45) / 0.55, 0.0, 1.0) ** 1.5
            sh = np.clip((0.60 - lum) / 0.60, 0.0, 1.0) ** 1.5
            arr = np.clip(arr + hi[..., None] * (value("highlights") / 220.0)
                          + sh[..., None] * (value("shadows") / 220.0), 0.0, 1.0)
            # Temperature (warm/cool) and tint (green/magenta).
            arr[..., 0] = np.clip(arr[..., 0] * (1.0 + value("temperature") / 500.0), 0.0, 1.0)
            arr[..., 2] = np.clip(arr[..., 2] * (1.0 - value("temperature") / 500.0), 0.0, 1.0)
            arr[..., 1] = np.clip(arr[..., 1] * (1.0 + value("tint") / 650.0), 0.0, 1.0)
            # Saturation and vibrance are separate: vibrance protects already vivid colors.
            gray = (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2])[..., None]
            sat_factor = max(0.0, 1.0 + value("saturation") / 100.0)
            arr = np.clip(gray + (arr - gray) * sat_factor, 0.0, 1.0)
            mx = arr.max(axis=2, keepdims=True)
            mn = arr.min(axis=2, keepdims=True)
            sat_map = (mx - mn) / np.maximum(mx, 1e-4)
            vib_factor = 1.0 + (value("vibrance") / 100.0) * (1.0 - sat_map)
            gray = (0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2])[..., None]
            arr = np.clip(gray + (arr - gray) * vib_factor, 0.0, 1.0)
            image = Image.fromarray(np.uint8(np.clip(arr * 255.0, 0, 255)), mode="RGB")
            if value("clarity") > 0:
                blurred = image.filter(ImageFilter.GaussianBlur(radius=2.0))
                image = Image.blend(blurred, image, 1.0 + value("clarity") / 100.0) if value("clarity") <= 0 else Image.blend(blurred, image, min(1.0, 0.5 + value("clarity") / 200.0))
            if value("sharpness") > 0:
                image = ImageEnhance.Sharpness(image).enhance(1.0 + value("sharpness") / 50.0)
            self.current = self._from_array(np.asarray(image, dtype=np.uint8))
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Adjustment unavailable", f"Could not apply adjustment.\\n\\n{exc}")

    def auto_adjust(self):
        """One-click, content-aware photo correction inspired by Canva Auto Adjust.

        Uses local Pillow/NumPy processing only: adaptive tonal range, exposure,
        restrained white-balance correction, vibrance and subtle sharpening.
        The source is kept in history so Undo/Reset remain non-destructive.
        """
        try:
            import numpy as np
            from PIL import Image, ImageEnhance, ImageFilter

            src = self._to_array().astype(np.float32) / 255.0
            # Work out luminance and robust percentiles, ignoring a few extreme pixels.
            lum = 0.2126 * src[..., 0] + 0.7152 * src[..., 1] + 0.0722 * src[..., 2]
            p_low, p_mid, p_high = np.percentile(lum, (1.0, 50.0, 99.0))
            span = max(float(p_high - p_low), 0.18)

            # Expand flat tonal ranges gently; avoid clipping already punchy images.
            target_low = max(0.0, float(p_low) - min(0.025, float(p_low) * 0.20))
            target_high = min(1.0, float(p_high) + min(0.025, (1.0-float(p_high)) * 0.20))
            gain = min(1.22, max(0.88, (target_high-target_low) / span))
            corrected = np.clip((src - float(p_low)) * gain + target_low, 0.0, 1.0)

            # Gentle exposure compensation toward a balanced midtone (not a fixed brighten).
            median = float(np.percentile(lum, 50.0))
            if median < 0.43:
                exposure = min(1.16, 0.43 / max(median, 0.08))
            elif median > 0.57:
                exposure = max(0.90, 0.57 / median)
            else:
                exposure = 1.0
            corrected = np.clip(corrected * exposure, 0.0, 1.0)

            # Subtle gray-world white balance, clamped so intentional color casts survive.
            channel_means = np.mean(corrected, axis=(0, 1))
            neutral = float(np.mean(channel_means))
            wb = np.clip(neutral / np.maximum(channel_means, 1e-4), 0.94, 1.06)
            corrected = np.clip(corrected * wb.reshape(1, 1, 3), 0.0, 1.0)

            # Lift shadow detail and gently compress highlights without flattening contrast.
            lum2 = (0.2126 * corrected[..., 0] + 0.7152 * corrected[..., 1] + 0.0722 * corrected[..., 2])
            shadow = np.clip((0.48-lum2) / 0.48, 0.0, 1.0)
            highlight = np.clip((lum2-0.68) / 0.32, 0.0, 1.0)
            corrected = np.clip(corrected + (shadow**2 * 0.035)[..., None] - (highlight**2 * 0.025)[..., None], 0.0, 1.0)

            # Vibrance: boost muted colors more than already-saturated colors.
            mx = corrected.max(axis=2, keepdims=True)
            mn = corrected.min(axis=2, keepdims=True)
            sat = (mx-mn) / np.maximum(mx, 1e-4)
            vibrance = 1.0 + 0.12 * (1.0-sat)
            gray = (0.2126*corrected[..., 0] + 0.7152*corrected[..., 1] + 0.0722*corrected[..., 2])[..., None]
            corrected = np.clip(gray + (corrected-gray)*vibrance, 0.0, 1.0)

            # Tiny clarity/sharpness touch; keep it subtle to avoid halos/noise.
            image = Image.fromarray(np.uint8(np.clip(corrected*255.0, 0, 255)), mode="RGB")
            # Canva-like finishing pass: subtle global contrast, colour and clarity.
            # Keep the correction restrained so faces and skin tones do not look artificial.
            from PIL import ImageOps
            image = ImageOps.autocontrast(image, cutoff=0.35)
            image = ImageEnhance.Contrast(image).enhance(1.045)
            image = ImageEnhance.Color(image).enhance(1.055)
            image = ImageEnhance.Sharpness(image).enhance(1.12)
            result = np.asarray(image, dtype=np.uint8)

            self._push_history()
            self.current = self._from_array(result)
            self.tone_base = self.current.copy()
            # Reflect the automatic correction in the controls (0 = original/no manual change).
            brightness_level = int(round(max(-25.0, min(25.0, (exposure - 1.0) * 100.0))))
            saturation_level = 12
            auto_values = {
                "brightness": brightness_level, "contrast": 5, "highlights": -3,
                "shadows": 5, "temperature": 0, "tint": 0, "saturation": 6,
                "vibrance": 12, "clarity": 8, "sharpness": 12,
            }
            self._tone_slider_baseline = dict(auto_values)
            for key, slider in self.adjustment_sliders.items():
                slider.blockSignals(True)
                slider.setValue(auto_values.get(key, 0))
                slider.blockSignals(False)
                self.adjustment_values[key].setText(str(slider.value()))
            self._refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Auto Adjust unavailable", f"Could not auto-adjust this image.\n\n{exc}")

    def remove_selection(self):
        box = self.preview.selection_in_image()
        if not box:
            QMessageBox.information(self, "Select an object", "Draw a rectangle around the object, leaving a little background visible around it. The app will identify the object inside the rectangle."); return
        x, y, w, h = box
        if w < 5 or h < 5:
            QMessageBox.information(self, "Selection too small", "Make the rectangle a little larger."); return
        if not _removal_assets_ready():
            choice = QMessageBox.question(
                self, "Download optional AI removal models?",
                "This feature needs a one-time download of the SAM 2.1 selection model, Big-LaMa background model and local AI runtime.\n\n"
                "They will be stored on this PC and reused automatically. Your image stays on this PC. Download and continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                return
        self._set_busy(True)
        self.progress = QProgressDialog("Preparing AI removal…", None, 0, 0, self)
        self.progress.setWindowTitle("Processing thumbnail")
        self.progress.setWindowModality(Qt.WindowModal)
        self.progress.setMinimumDuration(0)
        self.progress.show()
        from PySide6.QtCore import QTimer
        self._pending_remove = (self.current.copy(), box)
        QTimer.singleShot(0, self._start_remove_worker)

    def _start_remove_worker(self):
        if not hasattr(self, "_pending_remove"):
            return
        rgb, box = self._pending_remove
        del self._pending_remove
        self._inpaint_thread = InpaintThread(rgb, box, self)
        self._inpaint_thread.finished_image.connect(self._remove_done)
        self._inpaint_thread.failed.connect(self._remove_failed)
        self._inpaint_thread.status.connect(self.progress.setLabelText)
        self._inpaint_thread.start()

    def _start_enhance_worker(self):
        if not hasattr(self, "_pending_enhance"):
            return
        rgb = self._pending_enhance
        del self._pending_enhance
        self._enhance_thread = EnhanceThread(rgb, self)
        self._enhance_thread.finished_image.connect(self._enhance_done)
        self._enhance_thread.failed.connect(self._enhance_failed)
        self._enhance_thread.status.connect(self.progress.setLabelText)
        self._enhance_thread.start()

    def _set_busy(self, busy):
        for button in (self.remove_btn, self.auto_btn, self.enhance_btn, self.undo_btn, self.redo_btn, self.reset_btn, self.save_btn):
            button.setEnabled(not busy)

    def _finish_processing(self):
        if hasattr(self, "progress") and self.progress:
            self.progress.close()
        self._set_busy(False)

    def enhance_quality(self):
        if not _enhance_assets_ready():
            choice = QMessageBox.question(self, "Optional AI enhancement",
                "Enhance this thumbnail with Real-ESRGAN? The AI runtime and model need a one-time download and will stay on this PC.\n\nThe complete image will be fitted into a 1920 × 1080 canvas without stretching or cropping. Download and continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if choice != QMessageBox.Yes: return
        self._set_busy(True)
        self.progress = QProgressDialog("Preparing optional AI enhancement…", None, 0, 0, self)
        self.progress.setWindowTitle("Enhancing thumbnail")
        self.progress.setWindowModality(Qt.WindowModal); self.progress.setMinimumDuration(0); self.progress.show()
        from PySide6.QtCore import QTimer
        self._pending_enhance = self.current.copy()
        QTimer.singleShot(0, self._start_enhance_worker)

    def _enhance_done(self, arr):
        self._finish_processing(); self._push_history()
        self.current=self._from_array(arr); self.tone_base=self.current.copy()
        self._reset_sliders(); self._refresh()
        QMessageBox.information(self,"Enhancement complete","Saved in the editor as 1920 × 1080 (16:9). Use Save Copy to export it.")

    def _enhance_failed(self, message):
        self._finish_processing()
        QMessageBox.warning(self,"Enhancement unavailable",message)

    def _remove_done(self, arr):
        self._finish_processing(); self._push_history()
        self.current = self._from_array(arr); self.tone_base = self.current.copy()
        self._reset_sliders(); self._refresh()
        QMessageBox.information(self, "Removal complete", "The selected area has been processed. Review the result; use Undo if needed.")

    def _remove_failed(self, message):
        self._finish_processing()
        QMessageBox.warning(self, "Removal failed", f"Could not process the selected area.\n\n{message}")

    def undo(self):
        if self.history:
            self.redo_history.append(self.current.copy())
            self.current = self.history.pop()
            self.tone_base = self.current.copy()
            self._reset_sliders()
            self._refresh()

    def redo(self):
        if self.redo_history:
            self.history.append(self.current.copy())
            self.current = self.redo_history.pop()
            self.tone_base = self.current.copy()
            self._reset_sliders()
            self._refresh()

    def reset(self):
        if not self.current == self.original:
            self._push_history()
        self.current = self.original.copy()
        self.tone_base = self.current.copy()
        self._reset_sliders()
        self._refresh()

    def save_copy(self):
        suggested = self.image_path.with_name(self.image_path.stem + "_edited.jpg")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export thumbnail as JPG", str(suggested), "JPEG Image (*.jpg)")
        if path:
            if not path.lower().endswith((".jpg", ".jpeg")):
                path += ".jpg"
            image = self.current.convertToFormat(QImage.Format_RGB888)
            if not image.save(path, "JPG", 95):
                QMessageBox.warning(self, "Save failed", "Could not export the edited image as JPG.")
            else:
                QMessageBox.information(self, "Export complete", f"JPG thumbnail exported to:\n{path}")
