"""Generate build-time configuration from GitHub Actions environment."""
import os
from pathlib import Path

key = os.environ.get("YOUTUBE_API_KEY", "").strip()
repository = os.environ.get("GITHUB_REPOSITORY", "hemantHQ/Thumb-Finder").strip()
build_number = os.environ.get("THUMB_FINDER_BUILD_NUMBER", "1").strip()
if not key:
    raise SystemExit("Missing GitHub Actions secret: YOUTUBE_API_KEY")
if not repository or "/" not in repository:
    raise SystemExit("Invalid GitHub repository context.")
if not build_number.isdigit():
    raise SystemExit("THUMB_FINDER_BUILD_NUMBER must be an integer.")
Path("thumb_finder/api_config.py").write_text(
    "YOUTUBE_API_KEY = " + repr(key) + "\n"
    "GITHUB_REPOSITORY = " + repr(repository) + "\n"
    "BUILD_NUMBER = " + repr(int(build_number)) + "\n",
    encoding="utf-8",
)
