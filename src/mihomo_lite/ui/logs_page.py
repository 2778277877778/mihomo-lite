"""Full log view with copy/clear/open-folder helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.core.services import Services
from mihomo_lite.ui.widgets.log_view import LogView
from mihomo_lite.utils.logger import get_ring_buffer


class LogsPage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Logs")
        title.setObjectName("PageTitle")
        subtitle = QLabel("App and core output; secrets are redacted.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        header.addStretch(1)

        copy = QPushButton("Copy")
        copy.clicked.connect(self._copy)
        export = QPushButton("Export…")
        export.clicked.connect(self._export)
        clear = QPushButton("Clear view")
        clear.clicked.connect(self._clear)
        open_folder = QPushButton("Open log folder")
        open_folder.clicked.connect(self._open_folder)
        header.addWidget(copy)
        header.addWidget(export)
        header.addWidget(clear)
        header.addWidget(open_folder)
        root.addLayout(header)

        self._log = LogView(self)
        root.addWidget(self._log, 1)

    def _all_text(self) -> str:
        # The ring buffer already passed through SecretFilter.
        return "\n".join(text for _level, _name, text in get_ring_buffer().snapshot())

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._all_text())

    def _export(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export logs", "mihomo-lite-logs.txt", "Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        try:
            Path(path).write_text(self._all_text(), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _clear(self) -> None:
        self._log.clear_log()

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._services.paths.logs)))
