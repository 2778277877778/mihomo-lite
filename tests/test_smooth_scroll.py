from mihomo_lite.ui.widgets.smooth_scroll import SmoothScroller


class Bar:
    def singleStep(self) -> int:
        return 16


def test_pixel_delta_wins():
    assert SmoothScroller._wheel_step(24, 0, Bar()) == 24


def test_angle_delta_maps_to_lines():
    assert SmoothScroller._wheel_step(0, 120, Bar()) == 48
    assert SmoothScroller._wheel_step(0, -120, Bar()) == -48


def test_no_delta_is_zero():
    assert SmoothScroller._wheel_step(0, 0, Bar()) == 0


def test_small_single_step_is_raised():
    class Small:
        def singleStep(self) -> int:
            return 2

    assert SmoothScroller._wheel_step(0, 120, Small()) == 48
