from thumb_finder.release_control import evaluate_release


def test_live_switch_can_disable_app():
    state = evaluate_release({"enabled": False, "latest_version": "1.0.0"})
    assert state["allowed"] is False


def test_minimum_version_blocks_old_build():
    state = evaluate_release({
        "enabled": True, "latest_version": "2.0.0", "minimum_version": "1.5.0"
    }, "1.0.0")
    assert state["allowed"] is False
    assert state["update_available"] is True


def test_optional_update_does_not_block_startup():
    state = evaluate_release({
        "enabled": True, "latest_version": "1.1.0", "minimum_version": "1.0.0"
    }, "1.0.0")
    assert state["allowed"] is True
    assert state["update_available"] is True


def test_newest_version_starts_normally():
    state = evaluate_release({
        "enabled": True, "latest_version": "1.2.0", "minimum_version": "1.0.0"
    }, "1.2.0")
    assert state["allowed"] is True
    assert state["update_available"] is False



def test_invalid_version_data_does_not_crash():
    state = evaluate_release({
        "enabled": True, "latest_version": "not-a-version",
        "minimum_version": "also-invalid"
    }, "1.0.0")
    assert state["allowed"] is True


def test_disabled_message_and_release_url_are_preserved():
    state = evaluate_release({
        "enabled": False, "message": "Maintenance",
        "release_url": "https://example.com/release"
    })
    assert state["allowed"] is False
    assert state["message"] == "Maintenance"
    assert state["release_url"] == "https://example.com/release"
