"""Remote release availability and version policy for Thumb Finder.

The single source of truth is release-control.json in the GitHub repository.
Network failures are fail-open so a temporary GitHub outage does not lock users
out of the desktop app. Set enabled=false to disable app access remotely.
"""
from __future__ import annotations

import json
import logging
import os
import re
from urllib.request import Request, urlopen

CURRENT_VERSION = "1.0.0"
CONTROL_URL = (
    "https://raw.githubusercontent.com/hemantHQ/Thumb-Finder/main/release-control.json"
)


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    if not parts:
        raise ValueError("Version must contain at least one number.")
    return tuple(int(part) for part in parts)


def fetch_release_control(timeout: float = 2.5) -> dict:
    """Fetch the one-file remote policy; return safe defaults on network errors."""
    url = os.environ.get("THUMB_FINDER_CONTROL_URL", CONTROL_URL)
    request = Request(url, headers={"User-Agent": "ThumbFinder-Desktop"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(64 * 1024).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Release control must be a JSON object.")
        return payload
    except Exception:
        logging.warning("Could not fetch remote release control; allowing offline startup.", exc_info=True)
        return {
            "enabled": True,
            "latest_version": CURRENT_VERSION,
            "minimum_version": CURRENT_VERSION,
            "message": "Could not check online status. Starting in offline-safe mode.",
            "release_url": "https://github.com/hemantHQ/Thumb-Finder/releases/latest",
            "_offline": True,
        }


def evaluate_release(control: dict, current_version: str = CURRENT_VERSION) -> dict:
    """Return allowed/update/disabled state without making UI decisions."""
    latest = str(control.get("latest_version", current_version))
    minimum = str(control.get("minimum_version", "0"))
    try:
        update_available = _version_tuple(current_version) < _version_tuple(latest)
        below_minimum = _version_tuple(current_version) < _version_tuple(minimum)
    except ValueError:
        logging.warning("Invalid version in release-control.json; ignoring version gate.")
        update_available = below_minimum = False

    enabled = control.get("enabled", True) is True
    allowed = enabled and not below_minimum
    return {
        "allowed": allowed,
        "enabled": enabled,
        "update_available": update_available,
        "current_version": current_version,
        "latest_version": latest,
        "minimum_version": minimum,
        "message": str(control.get("message", "")),
        "release_url": str(control.get(
            "release_url",
            "https://github.com/hemantHQ/Thumb-Finder/releases/latest"
        )),
        "offline": bool(control.get("_offline", False)),
    }
