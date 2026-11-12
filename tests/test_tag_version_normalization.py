import re


def normalize_tag(tag):
    version = tag.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError(tag)
    return version if version.count(".") == 2 else version + ".0"


def test_two_part_release_tag_v1_0_normalizes_to_python_version():
    assert normalize_tag("v1.0") == "1.0.0"


def test_three_part_release_tag_remains_unchanged():
    assert normalize_tag("v1.0.1") == "1.0.1"


def test_invalid_tag_is_rejected():
    try:
        normalize_tag("v1")
    except ValueError:
        return
    raise AssertionError("Invalid release tag should be rejected")
