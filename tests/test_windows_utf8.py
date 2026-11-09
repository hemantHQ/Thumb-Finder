from pathlib import Path


def test_source_files_are_read_with_explicit_utf8():
    root = Path(__file__).parents[1]
    no_encoding_call = "read_text" + "()"
    for path in (root / "tests").glob("test_*.py"):
        source = path.read_text(encoding="utf-8")
        assert no_encoding_call not in source
