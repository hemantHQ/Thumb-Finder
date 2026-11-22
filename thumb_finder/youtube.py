from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import re
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from PIL import Image, ImageOps, ImageStat

REPOSITORY = "https://github.com/hemantHQ/Thumb-Finder"
ID_PATTERN = re.compile(r"[\w-]{11}", re.ASCII)
QUALITY = ("maxres", "standard", "high", "medium", "default")


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    channel: str
    views: int
    date: str
    seconds: int
    thumbnails: dict

    @property
    def url(self):
        return f"https://www.youtube.com/watch?v={self.id}"


def video_id(text):
    try:
        url = urlparse(text if "://" in text else f"https://{text}")
    except ValueError:
        return None
    host = url.hostname
    path = url.path.strip("/").split("/")
    candidate = ""
    if host == "youtu.be":
        candidate = path[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if path == ["watch"]:
            candidate = parse_qs(url.query).get("v", [""])[0]
        elif len(path) == 2 and path[0] in {"shorts", "live", "embed"}:
            candidate = path[1]
    return candidate if ID_PATTERN.fullmatch(candidate) else None


def duration(value):
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value)
    if not match:
        return 0
    return sum(int(number or 0) * unit for number, unit in zip(match.groups(), (86400, 3600, 60, 1)))


def quota_day():
    try:
        return datetime.now(ZoneInfo("America/Los_Angeles")).date()
    except ZoneInfoNotFoundError:
        return datetime.now().date()


class YouTube:
    def __init__(self, keys):
        self.keys = tuple(dict.fromkeys(key.strip() for key in keys if key.strip()))
        self.exhausted = set()
        self.day = quota_day()

    def request(self, endpoint, **params):
        if not self.keys:
            raise ValueError("Add a YouTube Data API key in Settings to search.")
        today = quota_day()
        if today != self.day:
            self.exhausted.clear()
            self.day = today
        errors = []
        for key in self.keys:
            if key in self.exhausted:
                continue
            try:
                response = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}",
                                        params={**params, "key": key}, timeout=(5, 15))
                body = response.json()
            except requests.RequestException:
                raise ValueError("Could not reach YouTube. Check your connection and try again.") from None
            except ValueError:
                raise ValueError("YouTube returned an unreadable response.") from None
            if response.ok:
                return body
            error = body.get("error", {})
            reasons = {entry.get("reason") for entry in error.get("errors", [])}
            reasons.update(entry.get("reason") for entry in error.get("details", []) if isinstance(entry, dict))
            if reasons & {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"}:
                self.exhausted.add(key)
                continue
            if reasons & {"keyInvalid", "API_KEY_INVALID", "accessNotConfigured", "SERVICE_DISABLED"}:
                errors.append("Check that your API keys are valid and YouTube Data API v3 is enabled.")
                continue
            raise ValueError(f"YouTube rejected the request (HTTP {response.status_code}). Check your key restrictions.")
        raise ValueError(errors[0] if errors else "The configured YouTube keys have exhausted their quota. Try again after the quota resets.")

    def page(self, query, minutes, genre, token=None):
        direct = video_id(query)
        if direct:
            ids, next_token = [direct], None
        else:
            params = dict(part="snippet", type="video", maxResults=24,
                          q=" ".join(filter(None, (query, genre, "full movie"))))
            if minutes >= 20:
                params["videoDuration"] = "long"
            if token:
                params["pageToken"] = token
            result = self.request("search", **params)
            ids = [item["id"]["videoId"] for item in result.get("items", [])]
            next_token = result.get("nextPageToken")
        if not ids:
            return [], next_token
        data = self.request("videos", part="snippet,contentDetails,statistics", id=",".join(ids))
        videos = []
        for row in data.get("items", []):
            snippet = row["snippet"]
            seconds = duration(row["contentDetails"]["duration"])
            if direct or seconds >= minutes * 60:
                videos.append(Video(row["id"], snippet["title"], snippet.get("channelTitle", ""),
                                    int(row.get("statistics", {}).get("viewCount", 0)),
                                    snippet.get("publishedAt", "")[:10], seconds, snippet["thumbnails"]))
        return videos, next_token


def thumbnail(video, preview=False):
    order = ("medium", "high", "standard", "maxres", "default") if preview else QUALITY
    for size in order:
        url = video.thumbnails.get(size, {}).get("url")
        if not url:
            continue
        try:
            response = requests.get(url, timeout=(4, 8))
            if response.ok:
                with Image.open(BytesIO(response.content)) as image:
                    image.verify()
                return response.content
        except (requests.RequestException, OSError, Image.DecompressionBombError):
            continue
    raise ValueError("The thumbnail could not be downloaded.")


def signature(data):
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB").resize((40, 40))
    gray = image.convert("L").resize((9, 8))
    pixels = gray.tobytes()
    edges = [pixels[y * 9 + x] > pixels[y * 9 + x + 1] for y in range(8) for x in range(8)]
    histogram = [sum(channel[i:i + 32]) / 1600 for channel in
                 (band.histogram() for band in image.split()) for i in range(0, 256, 32)]
    return edges, histogram, ImageStat.Stat(image).mean


def distance(first, second):
    edges, histogram, mean = first
    other_edges, other_histogram, other_mean = second
    return (
        0.5 * sum(a != b for a, b in zip(edges, other_edges)) / 64
        + 0.4 * sum(abs(a - b) for a, b in zip(histogram, other_histogram)) / 6
        + 0.1 * sum(abs(a - b) for a, b in zip(mean, other_mean)) / 765
    )
