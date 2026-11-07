"""Full log view with copy/clear/open-folder helpers."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mihomo_lite.core.services import Services
from mihomo_lite.ui.widgets.log_view import LogView


class LogsPage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Logs")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Application and core output. API secrets are redacted automatically.")
        subtitle.setObjectName("PageSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        clear = QPushButton("Clear view")
        clear.clicked.connect(self._clear)
        open_folder = QPushButton("Open log folder")
        open_folder.clicked.connect(self._open_folder)
        header.addWidget(clear)
        header.addWidget(open_folder)
        root.addLayout(header)

        self._log = LogView(self)
        root.addWidget(self._log, 1)

    def _clear(self) -> None:
        self._log.clear_log()

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._services.paths.logs)))
