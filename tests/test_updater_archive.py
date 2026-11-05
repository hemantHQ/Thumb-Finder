import zipfile
from pathlib import Path

import pytest

from thumb_finder.updater import validate_archive


def test_windows_portable_archive_has_expected_root(tmp_path: Path):
    archive = tmp_path / "windows.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Thumb-Finder/Thumb-Finder.exe", "binary")
    validate_archive(archive, "windows")


def test_macos_portable_archive_has_expected_root(tmp_path: Path):
    archive = tmp_path / "mac.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Thumb Finder.app/Contents/MacOS/Thumb Finder", "binary")
    validate_archive(archive, "macos-intel")


def test_update_archive_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Thumb-Finder/../outside.txt", "unsafe")
    with pytest.raises(ValueError, match="unsafe file path"):
        validate_archive(archive, "windows")
