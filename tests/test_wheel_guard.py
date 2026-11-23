from mihomo_lite.ui.widgets.wheel_guard import WheelGuard


def test_wheel_delta_follows_notches():
    assert WheelGuard._scroll_delta(120, 16) == 48
    assert WheelGuard._scroll_delta(-120, 16) == -48
    assert WheelGuard._scroll_delta(240, 16) == 96


def test_wheel_delta_raises_small_steps():
    assert WheelGuard._scroll_delta(120, 1) == 48


def test_zero_angle_does_nothing():
    assert WheelGuard._scroll_delta(0, 16) == 0
