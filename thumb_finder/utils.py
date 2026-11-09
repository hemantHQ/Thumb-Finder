"""Small dependency-free helpers shared by the app and unit tests."""
import re

_DURATION_PATTERN = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_youtube_duration(value: str | None) -> int:
    """Convert a YouTube ISO-8601 duration (for example PT1H20M) to seconds."""
    match = _DURATION_PATTERN.fullmatch(value or "")
    if not match:
        return 0
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds
