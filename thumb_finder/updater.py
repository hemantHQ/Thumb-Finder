"""Cross-platform updater for portable Windows and macOS builds."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def install_root() -> Path:
    """Return the portable app directory or macOS .app bundle."""
    executable = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.name.endswith(".app"):
                return parent
    return executable.parent


def platform_key() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos-intel"
    raise RuntimeError("Automatic updates are supported only on Windows and Intel macOS.")


def validate_archive(archive: Path, platform: str) -> None:
    """Reject unsafe paths and unexpected top-level content before extraction."""
    expected = "Thumb-Finder/" if platform == "windows" else "Thumb Finder.app/"
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        if not names or not any(name.startswith(expected) for name in names):
            raise ValueError("The update package has an unexpected folder structure.")
        for name in names:
            normalized = name.replace("\\", "/")
            p = PurePosixPath(normalized)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError("The update package contains an unsafe file path.")


def launch_update_helper(archive: Path, process_id: int) -> None:
    """Launch a native OS helper that replaces the app after it exits."""
    root = install_root()
    platform = platform_key()
    if not root.exists() or not os.access(root.parent, os.W_OK):
        raise PermissionError(
            "Thumb Finder is installed in a protected location. Move the portable app "
            "to a folder writable by your user account, then run the update again."
        )
    validate_archive(archive, platform)
    helper_dir = Path(tempfile.mkdtemp(prefix="thumb_finder_update_"))

    if platform == "windows":
        script = helper_dir / "apply_update.ps1"
        script.write_text(r'''param([int]$ProcessId, [string]$Archive, [string]$Target)
$ErrorActionPreference = "Stop"
try {
    try { Wait-Process -Id $ProcessId -ErrorAction SilentlyContinue } catch {}
    $parent = Split-Path -Parent $Target
    $stage = Join-Path $parent (".thumb_finder_stage_" + [guid]::NewGuid().ToString("N"))
    $backup = Join-Path $parent (".thumb_finder_backup_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $stage | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $stage -Force
    $newApp = Join-Path $stage "Thumb-Finder"
    if (!(Test-Path (Join-Path $newApp "Thumb-Finder.exe"))) { throw "Portable executable missing from update." }
    Move-Item -LiteralPath $Target -Destination $backup
    try { Move-Item -LiteralPath $newApp -Destination $Target }
    catch { Move-Item -LiteralPath $backup -Destination $Target; throw }
    Start-Process -FilePath (Join-Path $Target "Thumb-Finder.exe")
    Start-Sleep -Seconds 2
    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Add-Content -LiteralPath (Join-Path $env:USERPROFILE ".thumb_finder\update_error.log") $_.ToString()
    exit 1
}
''', encoding="utf-8")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File",
             str(script), str(process_id), str(archive), str(root)],
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0),
            close_fds=True,
        )
        return

    script = helper_dir / "apply_update.sh"
    script.write_text(r'''#!/bin/bash
set -euo pipefail
PID="$1"; ARCHIVE="$2"; TARGET="$3"
LOG="$HOME/.thumb_finder/update_error.log"
mkdir -p "$HOME/.thumb_finder"
trap 'echo "Updater failed at $(date)" >> "$LOG"' ERR
while kill -0 "$PID" 2>/dev/null; do sleep 1; done
PARENT="$(dirname "$TARGET")"
STAGE="$(mktemp -d "$PARENT/.thumb_finder_stage.XXXXXX")"
BACKUP="$PARENT/.thumb_finder_backup.$$.app"
cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT
/usr/bin/ditto -x -k "$ARCHIVE" "$STAGE"
NEW_APP="$STAGE/Thumb Finder.app"
test -d "$NEW_APP/Contents/MacOS"
mv "$TARGET" "$BACKUP"
if ! mv "$NEW_APP" "$TARGET"; then mv "$BACKUP" "$TARGET"; exit 1; fi
open "$TARGET"
sleep 2
rm -rf "$BACKUP"
''', encoding="utf-8")
    script.chmod(0o700)
    subprocess.Popen(
        ["/bin/bash", str(script), str(process_id), str(archive), str(root)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )
