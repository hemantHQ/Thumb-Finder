"""Generate build-time configuration from GitHub Actions environment."""
import os
from pathlib import Path

key = os.environ.get("YOUTUBE_API_KEY", "").strip()
repository = os.environ.get("GITHUB_REPOSITORY", "").strip()

if not key:
    raise SystemExit("Missing GitHub Actions secret: YOUTUBE_API_KEY")
if not repository or "/" not in repository:
    raise SystemExit("Missing GitHub Actions repository context.")

Path("thumb_finder/api_config.py").write_text(
    "YOUTUBE_API_KEY = " + repr(key) + "\n"
    "GITHUB_REPOSITORY = " + repr(repository) + "\n",
    encoding="utf-8",
)
