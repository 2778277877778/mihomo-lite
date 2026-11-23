import pytest

from mihomo_lite.ui.widgets import smooth_scroll
from mihomo_lite.ui.widgets.smooth_scroll import SmoothScroller, set_scroll_inverted

WHEEL = smooth_scroll._WHEEL_VELOCITY
GAIN = smooth_scroll._TRACKPAD_GAIN


def test_wheel_notch_converts_to_velocity():
    assert SmoothScroller._velocity_from(120, 0) == pytest.approx(WHEEL)
    assert SmoothScroller._velocity_from(-120, 0) == pytest.approx(-WHEEL)
    assert SmoothScroller._velocity_from(240, 0) == pytest.approx(WHEEL * 2)


def test_trackpad_pixels_are_gain_scaled():
    assert SmoothScroller._velocity_from(0, 40) == pytest.approx(40 * GAIN)
    assert SmoothScroller._velocity_from(0, -40) == pytest.approx(-40 * GAIN)


def test_no_delta_means_no_motion():
    assert SmoothScroller._velocity_from(0, 0) == 0.0


def test_vertical_motion_matches_the_wheel_direction():
    assert SmoothScroller._axis_delta(5.0, horizontal=False) == -5.0
    assert SmoothScroller._axis_delta(-5.0, horizontal=False) == 5.0


def test_horizontal_motion_keeps_its_sign():
    assert SmoothScroller._axis_delta(5.0, horizontal=True) == 5.0


def test_inverted_setting_flips_both_axes():
    set_scroll_inverted(True)
    try:
        assert SmoothScroller._axis_delta(5.0, horizontal=False) == 5.0
        assert SmoothScroller._axis_delta(5.0, horizontal=True) == -5.0
    finally:
        set_scroll_inverted(False)
