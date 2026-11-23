from PySide6.QtCore import QObject, Signal

from mihomo_lite.core.traffic_monitor import TrafficSample
from mihomo_lite.core.traffic_stats import TrafficStats


class FakeTraffic(QObject):
    sample = Signal(object)


def make_stats(paths, qapp, clock=None):
    return TrafficStats(paths, FakeTraffic(), clock=clock or (lambda: 1000.0))


def emit(traffic_source, up, down, up_total, down_total):
    traffic_source.sample.emit(
        TrafficSample(up=up, down=down, up_total=up_total, down_total=down_total)
    )


def test_accumulates_deltas_and_peaks(paths, qapp):
    traffic = FakeTraffic()
    stats = TrafficStats(paths, traffic, clock=lambda: 1000.0)
    emit(traffic, 100, 200, 100, 200)
    emit(traffic, 50, 300, 150, 500)

    snapshot = stats.snapshot
    assert snapshot.today_down == 500
    assert snapshot.today_up == 150
    assert snapshot.session_down == 500
    assert snapshot.session_up == 150
    assert snapshot.peak_down == 300
    assert snapshot.peak_up == 100
    assert len(snapshot.samples) == 2


def test_reset_today_keeps_session(paths, qapp):
    traffic = FakeTraffic()
    stats = TrafficStats(paths, traffic, clock=lambda: 1000.0)
    emit(traffic, 10, 20, 10, 20)
    stats.reset_today()
    snapshot = stats.snapshot
    assert snapshot.today_down == 0
    assert snapshot.session_down == 20


def test_totals_persist_across_restarts(paths, qapp):
    traffic = FakeTraffic()
    stats = TrafficStats(paths, traffic, clock=lambda: 0.0)
    emit(traffic, 10, 20, 10, 20)
    stats.flush()

    reloaded = TrafficStats(paths, FakeTraffic(), clock=lambda: 0.0)
    assert reloaded.snapshot.today_down == 20
    assert reloaded.snapshot.today_up == 10
