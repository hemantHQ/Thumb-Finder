"""Install the optional CPU engine and launch it outside the GUI process."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import platform
import subprocess
import sys
import tarfile

import requests

from . import studio


@dataclass(frozen=True)
class Model:
    label: str
    megabytes: int
    url: str
    digest: str


MODELS = {
    "remove": Model("LaMa", 208, "https://huggingface.co/Carve/LaMa-ONNX/resolve/c3c0c9e46893/lama_fp32.onnx",
                    "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6"),
    "enhance": Model("Real-ESRGAN", 68,
                     "https://huggingface.co/SceneWorks/real-esrgan-onnx/resolve/09f741b/real_esrgan_x2.onnx",
                     "7115ba92e8a1bfa63d68558ef006ef3d91273a068d321b1439f8bb1c9179002c"),
}
PYTHON_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/20261110/"
              "cpython-3.11.18%2B20261110-aarch64-apple-darwin-install_only.tar.gz")
PYTHON_HASH = "73f1ed14486aa278d331e95f7d6d452f5cfb69d90b418e26e62fd4846d53557d"
FROZEN = getattr(sys, "frozen", False)
VERSION = (3, 11) if FROZEN else sys.version_info[:2]
RUNTIME = "runtime-ort1311-py{}{}-{}".format(*VERSION, platform.machine())


def model_path(root, tool):
    return root / f"{tool}-{MODELS[tool].digest[:12]}.onnx"


def delete_model(root, tool):
    model_path(root, tool).unlink(missing_ok=True)


def ready(root, tool):
    return (root / RUNTIME / ".ready").is_file() and model_path(root, tool).is_file()


def download(url, destination, digest, report, stop, title, max_bytes):
    target_hash = sha256()
    size = 0
    last_percent = -1
    try:
        with requests.get(url, stream=True, timeout=(8, 30)) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            if total > max_bytes:
                raise ValueError(f"The {title} download is larger than expected.")
            with destination.open("wb") as file:
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if stop.is_set():
                        raise ValueError("Setup canceled.")
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError(f"The {title} download is larger than expected.")
                    target_hash.update(chunk)
                    file.write(chunk)
                    if total:
                        percent = min(100, size * 100 // total)
                        if percent != last_percent:
                            report(f"Downloading {title}… {percent}%")
                            last_percent = percent
    except requests.RequestException:
        raise ValueError(f"Could not download {title}. Check your connection and try again.") from None
    if target_hash.hexdigest() != digest:
        raise ValueError(f"The {title} download failed its integrity check. Try again.")


def run_command(args, timeout, stage):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("PYTHON", "PIP_")) and key not in {"DYLD_LIBRARY_PATH", "LD_LIBRARY_PATH"}}
    env["ORT_DISABLE_TELEMETRY"] = "1"
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run([str(arg) for arg in args], env=env, capture_output=True, text=True,
                                errors="replace", timeout=timeout, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError(f"{stage} could not finish. Check available disk space and try again.") from None
    if result.returncode:
        details = (result.stderr or result.stdout).strip().splitlines()
        raise ValueError(f"{stage} failed." + (f" {details[-1][:180]}" if details else ""))


def python_path(root):
    return root / "python" / "bin" / "python3" if FROZEN else Path(sys.executable)


def install(root, tool, report, stop):
    if ready(root, tool):
        return
    root.mkdir(parents=True, exist_ok=True)
    installed = root / RUNTIME
    model = MODELS[tool]
    with TemporaryDirectory(prefix="setup-", dir=root) as directory:
        staging = Path(directory)
        if not (installed / ".ready").is_file():
            runtime = staging / "runtime"
            runtime.mkdir()
            if FROZEN:
                if sys.platform != "darwin" or platform.machine() != "arm64":
                    raise ValueError("The packaged AI runtime supports Apple Silicon. On Windows, use the source launcher.")
                archive = staging / "python.tar.gz"
                report("Downloading the AI runtime…")
                download(PYTHON_URL, archive, PYTHON_HASH, report, stop, "the AI runtime", 40_000_000)
                with tarfile.open(archive, "r:gz") as bundle:
                    bundle.extractall(runtime, filter="data")
            python = python_path(runtime)
            report("Installing the shared AI engine…")
            run_command([python, "-I", "-m", "pip", "--isolated", "--disable-pip-version-check", "install",
                         "--index-url", "https://pypi.org/simple", "--only-binary=:all:", "--no-input",
                         "--retries", "2", "--target", runtime / "packages",
                         "onnxruntime==1.31.1", "Pillow>=11,<13"], 240, "AI engine setup")
            run_command([python, "-I", "-c",
                         "import sys; sys.path.insert(0, sys.argv[1]); import onnxruntime, PIL",
                         runtime / "packages"], 35, "AI engine verification")
            (runtime / ".ready").touch()
            try:
                runtime.rename(installed)
            except OSError:
                if not (installed / ".ready").is_file():
                    raise
        target = model_path(root, tool)
        if not target.is_file():
            report(f"Downloading {model.label}…")
            temporary = staging / "model.onnx"
            download(model.url, temporary, model.digest, report, stop, model.label,
                     (model.megabytes + 20) * 1_000_000)
            temporary.replace(target)


def process(root, image, selection, report, stop):
    from .services import repair_masks

    tool = "remove" if selection else "enhance"
    if not ready(root, tool):
        raise ValueError("Download the model before using this tool.")
    if stop.is_set():
        raise ValueError("AI edit canceled.")
    runtime = root / RUNTIME
    with TemporaryDirectory(prefix="edit-", dir=root) as directory:
        folder = Path(directory)
        original, output = (folder / filename for filename in ("source.png", "result.png"))
        image.save(original)
        masks = []
        if selection:
            for index, mask in enumerate(repair_masks(image.size, selection)):
                path = folder / f"mask-{index}.png"
                mask.save(path)
                masks.append(path)
            if not masks:
                raise ValueError("Mark an area on the image before applying removal.")
        report("Rebuilding the selected area…" if selection else "Enhancing to 1920 × 1080…")
        run_command([python_path(runtime), "-I", Path(__file__).with_name("offline_worker.py"),
                     runtime / "packages", tool, model_path(root, tool), original, output, *masks],
                    240, "Local AI edit")
        data = output.read_bytes()
        expected = image.size if selection else studio.FHD
        if studio.open_image(data).size != expected:
            raise ValueError("The AI engine returned an image with unexpected dimensions.")
        return data
