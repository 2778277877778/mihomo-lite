"""Traffic page: live speeds, session/today totals and a rolling chart."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core.services import Services
from mihomo_lite.core.traffic_monitor import TrafficSample, human_bytes, human_speed
from mihomo_lite.ui.widgets.status import KeyValueRow, MetricTile
from mihomo_lite.ui.widgets.traffic_chart import TrafficChart


class TrafficPage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._build()
        services.traffic.sample.connect(self._on_sample)
        services.stats.updated.connect(self._on_stats)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Traffic")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Live speed, session totals and today's usage.")
        subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self._reset_button = QPushButton("Reset today")
        self._reset_button.clicked.connect(self._services.stats.reset_today)
        header.addWidget(self._reset_button)
        root.addLayout(header)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self._down = MetricTile("Download", "0 B/s")
        self._up = MetricTile("Upload", "0 B/s")
        self._session = MetricTile("Session", "0 B")
        self._today = MetricTile("Today", "0 B")
        for tile in (self._down, self._up, self._session, self._today):
            tiles.addWidget(tile)
        root.addLayout(tiles)

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)
        chart_title = QLabel("Last 2 minutes")
        chart_title.setObjectName("MetricLabel")
        card_layout.addWidget(chart_title)
        self._chart = TrafficChart(self)
        card_layout.addWidget(self._chart, 1)
        root.addWidget(card, 1)

        details = QFrame()
        details.setObjectName("Card")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(20, 12, 20, 12)
        details_layout.setSpacing(2)
        self._today_row = KeyValueRow("Today download / upload")
        self._peak_row = KeyValueRow("Peak speed (session)")
        details_layout.addWidget(self._today_row)
        details_layout.addWidget(self._peak_row)
        root.addWidget(details)

    def _on_sample(self, sample: TrafficSample) -> None:
        self._down.set_value(human_speed(sample.down))
        self._up.set_value(human_speed(sample.up))
        self._session.set_value(human_bytes(sample.down_total + sample.up_total))

    def _on_stats(self, snapshot: object) -> None:
        today = getattr(snapshot, "today_down", 0) + getattr(snapshot, "today_up", 0)
        self._today.set_value(human_bytes(today))
        self._today_row.set_value(
            f"↓ {human_bytes(getattr(snapshot, 'today_down', 0))}  ·  "
            f"↑ {human_bytes(getattr(snapshot, 'today_up', 0))}"
        )
        self._peak_row.set_value(
            f"↓ {human_speed(getattr(snapshot, 'peak_down', 0))}  ·  "
            f"↑ {human_speed(getattr(snapshot, 'peak_up', 0))}"
        )
        self._chart.set_samples(tuple(getattr(snapshot, "samples", ())))
