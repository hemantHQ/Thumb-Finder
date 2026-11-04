from thumb_finder.app import version_tuple


def test_version_tuple_orders_patch_versions():
    assert version_tuple("1.0.1") > version_tuple("1.0.0")


def test_version_tuple_treats_trailing_zero_as_equal():
    assert version_tuple("1.0") == version_tuple("1.0.0")
