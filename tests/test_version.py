from pathlib import Path
from thumb_finder.version import __version__


def test_version_is_semver_like():
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_visible_app_branding_stays_v10():
    app_source = (Path(__file__).parents[1] / "thumb_finder" / "app.py").read_text(encoding="utf-8")
    assert 'QLabel("Thumb Finder v1.0")' in app_source
