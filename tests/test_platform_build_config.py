from pathlib import Path


def test_workflow_builds_both_macos_architectures_and_icons():
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "release-build.yml").read_text(encoding="utf-8")
    assert "macos-15-intel" in workflow
    assert "macos-15" in workflow
    assert "--target-architecture" in workflow
    assert "iconutil -c icns" in workflow
    assert "--icon" in workflow and "app_icon.icns" in workflow
    assert "app_icon.ico" in workflow


def test_platform_icon_assets_are_present():
    root = Path(__file__).parents[1] / "thumb_finder"
    assert (root / "app_icon.svg").is_file()
    assert (root / "app_icon.png").is_file()
    assert (root / "app_icon.ico").is_file()
