import pytest

from mihomo_lite.ui.widgets.smooth_scroll import SmoothScroller, set_scroll_inverted


def test_wheel_notch_converts_to_velocity():
    assert SmoothScroller._velocity_from(120, 0) == pytest.approx(5.0)
    assert SmoothScroller._velocity_from(-120, 0) == pytest.approx(-5.0)
    assert SmoothScroller._velocity_from(240, 0) == pytest.approx(10.0)


def test_trackpad_pixels_are_gain_scaled():
    assert SmoothScroller._velocity_from(0, 40) == pytest.approx(3.2)
    assert SmoothScroller._velocity_from(0, -40) == pytest.approx(-3.2)


def test_no_delta_means_no_motion():
    assert SmoothScroller._velocity_from(0, 0) == 0.0


def test_vertical_motion_matches_the_wheel_direction():
    # Positive (wheel forward / fingers up) scrolls towards the top of the list.
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
