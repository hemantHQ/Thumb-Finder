"""Write the YouTube API key supplied by the release CI environment."""
import os
from pathlib import Path

key = os.environ.get("YOUTUBE_API_KEY", "").strip()
if not key:
    raise SystemExit("Missing GitHub Actions secret: YOUTUBE_API_KEY")

Path("thumb_finder/api_config.py").write_text(
    "YOUTUBE_API_KEY = " + repr(key) + "\\n",
    encoding="utf-8",
)
