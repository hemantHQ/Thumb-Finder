"""Create a platform/build manifest for the in-app updater."""
import hashlib
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thumb_finder.version import __version__

build = int(os.environ.get("THUMB_FINDER_BUILD_NUMBER", "0"))
assets = {
    "windows": "Thumb-Finder-Windows-Portable.zip",
    "macos-intel": "Thumb-Finder-macOS-Intel-Portable.zip",
}
checksums = {}
for platform, filename in assets.items():
    path = Path("release-assets") / filename
    if not path.is_file():
        raise SystemExit(f"Missing update archive: {path}")
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    checksums[platform] = hasher.hexdigest()
manifest = {
    "version": __version__,
    "build": build,
    "assets": assets,
    "sha256": checksums,
}
Path("release-assets/thumb-finder-update.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(manifest, indent=2))
