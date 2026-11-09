from thumb_finder.utils import parse_youtube_duration


def test_parse_movie_duration_hours_and_minutes():
    assert parse_youtube_duration("PT1H40M") == 6000


def test_parse_movie_duration_minutes_only():
    assert parse_youtube_duration("PT45M") == 2700


def test_parse_movie_duration_with_seconds():
    assert parse_youtube_duration("PT1H2M3S") == 3723


def test_invalid_duration_returns_zero():
    assert parse_youtube_duration("not-a-duration") == 0
    assert parse_youtube_duration(None) == 0
