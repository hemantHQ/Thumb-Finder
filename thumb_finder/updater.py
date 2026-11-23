"""Verify and install macOS updates from the configured GitHub release repository."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from tempfile import mkdtemp
from urllib.parse import urlsplit
from zipfile import ZipFile
import os
import plistlib
import posixpath
import re
import shutil
import stat
import subprocess
import sys

import requests

BUNDLE = "Thumb Finder.app"
IDENTIFIER = "com.thumbfinder.app"
MAX_ZIP = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
ALLOWED_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


@dataclass(frozen=True)
class Release:
    tag: str
    url: str
    digest: str
    size: int


def build_number(tag):
    match = re.fullmatch(r"v1\.0-build-([1-9][0-9]*)", tag)
    return int(match[1]) if match else None


def check(repository, installed):
    slug = urlsplit(repository).path.strip("/")
    api = f"https://api.github.com/repos/{slug}/releases/latest"
    response = requests.get(api, timeout=(5, 12), allow_redirects=False)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError("GitHub did not return release information.")
    info = response.json()
    tag = info.get("tag_name", "")
    build = build_number(tag)
    if build is None or build <= installed:
        return None
    name = f"Thumb-Finder-{tag}-macOS-arm64.zip"
    url = f"{repository}/releases/download/{tag}/{name}"
    for item in info.get("assets", []):
        digest = item.get("digest") or ""
        size = item.get("size", 0)
        if (item.get("name") == name and item.get("browser_download_url") == url
                and item.get("state") == "uploaded" and type(size) is int
                and 0 < size <= MAX_ZIP and re.fullmatch(r"sha256:[a-f0-9]{64}", digest)):
            return Release(tag, url, digest[7:], size)
    return Release(tag, "", "", 0)


def installed_bundle():
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return None
    app = Path(sys.executable).resolve().parent.parent.parent
    return app if app.suffix == ".app" and app.parent in (Path("/Applications"), Path.home() / "Applications") else None


def fetch(release, archive):
    url = release.url
    digest = sha256()
    received = 0
    for _ in range(5):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
                or parsed.port not in (443, None) or parsed.username is not None):
            raise ValueError("GitHub redirected the download to an unexpected address.")
        with requests.get(url, stream=True, timeout=(8, 30), allow_redirects=False) as response:
            if response.is_redirect:
                url = response.headers["Location"]
                continue
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError("GitHub did not return the update ZIP.")
            with archive.open("wb") as file:
                for chunk in response.iter_content(1024 * 1024):
                    received += len(chunk)
                    if received > release.size:
                        raise ValueError("The update ZIP is larger than expected.")
                    digest.update(chunk)
                    file.write(chunk)
            if received != release.size or digest.hexdigest() != release.digest:
                raise ValueError("The update ZIP failed its integrity check.")
            return
    raise ValueError("The update download redirected too many times.")


def check_archive(archive):
    with ZipFile(archive) as zipped:
        total = 0
        members = set()
        symlinks = set()
        for item in zipped.infolist():
            path = PurePosixPath(item.filename)
            if (not path.parts or path.parts[0] != BUNDLE or ".." in path.parts
                    or "\\" in item.filename or path in members):
                raise ValueError("The update ZIP contains an unexpected path.")
            members.add(path)
            total += item.file_size
            if total > MAX_EXPANDED:
                raise ValueError("The expanded update is larger than expected.")
            kind = stat.S_IFMT(item.external_attr >> 16)
            if kind == stat.S_IFLNK:
                if item.file_size > 2048:
                    raise ValueError("The update ZIP contains an invalid link.")
                target = zipped.read(item).decode("utf-8")
                resolved = posixpath.normpath(posixpath.join(str(path.parent), target))
                if not target or "\\" in target or not resolved.startswith(BUNDLE + "/"):
                    raise ValueError("The update ZIP contains a link outside the app.")
                symlinks.add(path)
            elif kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError("The update ZIP contains an unsupported file type.")
        if any(parent in symlinks for path in members for parent in path.parents):
            raise ValueError("The update ZIP contains files nested beneath a link.")
        if PurePosixPath(BUNDLE, "Contents", "Info.plist") not in members:
            raise ValueError("The update ZIP is missing the macOS app.")


def verify_bundle(candidate, tag):
    contents = candidate / "Contents"
    with (contents / "Info.plist").open("rb") as file:
        info = plistlib.load(file)
    build = contents / "Resources" / "thumb_finder" / "build_version.txt"
    if (info.get("CFBundleIdentifier") != IDENTIFIER or info.get("CFBundleExecutable") != "Thumb Finder"
            or build.read_text(encoding="utf-8").strip() != str(build_number(tag))):
        raise ValueError("The downloaded app does not match the release.")
    with (contents / "MacOS" / "Thumb Finder").open("rb") as file:
        if file.read(8) != bytes.fromhex("cffaedfe0c000001"):
            raise ValueError("The downloaded app does not contain an Apple Silicon executable.")
    subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", candidate],
                   check=True, capture_output=True, timeout=60)


def prepare(release, installed):
    try:
        stage = Path(mkdtemp(prefix=".thumb-finder-update-", dir=installed.parent))
    except PermissionError:
        raise ValueError("Thumb Finder cannot write to this Applications folder. Install the release ZIP manually.") from None
    try:
        archive = stage / "release.zip"
        fetch(release, archive)
        check_archive(archive)
        subprocess.run(["/usr/bin/ditto", "-x", "-k", archive, stage], check=True, timeout=60)
        verify_bundle(stage / BUNDLE, release.tag)
        archive.unlink()
        return stage
    except Exception:
        shutil.rmtree(stage)
        raise


INSTALL = """#!/bin/sh
set -eu
pid=$1
current=$2
stage=$3
old="$stage/Previous Thumb Finder.app"
new="$stage/Thumb Finder.app"
attempts=0
while kill -0 "$pid" 2>/dev/null; do
    attempts=$((attempts + 1))
    [ "$attempts" -lt 120 ] || exit 1
    sleep 1
done
if /usr/bin/xattr -p com.apple.quarantine "$current" > "$stage/quarantine" 2>/dev/null; then
    /usr/bin/xattr -w com.apple.quarantine "$(cat "$stage/quarantine")" "$new"
fi
test -d "$new"
test ! -e "$old"
mv "$current" "$old"
if ! mv "$new" "$current"; then
    mv "$old" "$current"
    /usr/bin/open "$current"
    exit 1
fi
if ! /usr/bin/open -n "$current"; then
    mv "$current" "$new"
    mv "$old" "$current"
    /usr/bin/open "$current"
    exit 1
fi
"""


def restart(stage, installed):
    script = stage / "install.sh"
    script.write_text(INSTALL, encoding="utf-8")
    with (stage / "install.log").open("wb") as log:
        subprocess.Popen(["/bin/sh", script, str(os.getpid()), installed, stage],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
