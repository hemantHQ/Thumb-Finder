from pathlib import Path

_build = Path(__file__).with_name("build_version.txt")
VERSION = "1.0"
BUILD = int(_build.read_text(encoding="utf-8").strip()) if _build.is_file() else 0
