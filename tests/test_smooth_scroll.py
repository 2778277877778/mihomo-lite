import pytest

from mihomo_lite.ui.widgets.smooth_scroll import SmoothScroller


def test_wheel_notch_converts_to_velocity():
    assert SmoothScroller._velocity_from(120, 0) == pytest.approx(5.0)
    assert SmoothScroller._velocity_from(-120, 0) == pytest.approx(-5.0)
    assert SmoothScroller._velocity_from(240, 0) == pytest.approx(10.0)


def test_trackpad_pixels_are_gain_scaled():
    assert SmoothScroller._velocity_from(0, 40) == pytest.approx(3.2)
    assert SmoothScroller._velocity_from(0, -40) == pytest.approx(-3.2)


def test_no_delta_means_no_motion():
    assert SmoothScroller._velocity_from(0, 0) == 0.0
