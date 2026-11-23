"""Profile list: import a local YAML, add a subscription, switch and refresh."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.config.loader import load_yaml_file
from mihomo_lite.config.rules import analyze_rules
from mihomo_lite.core import qr
from mihomo_lite.core.services import Services
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.models.profile import Profile, ProfileKind
from mihomo_lite.ui.widgets.smooth_scroll import enable_smooth_scroll
from mihomo_lite.utils.logger import redact_url


class ProfilePage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._build()
        services.profiles.profiles_changed.connect(self._reload)
        services.profiles.active_changed.connect(lambda _p: self._reload())
        services.updates.started.connect(self._on_update_started)
        services.updates.finished.connect(self._on_update_finished)
        services.updates.profile_failed.connect(self._on_update_failed)
        services.updates.active_profile_updated.connect(self._on_active_updated)
        services.connection.state_changed.connect(self._on_state)
        self._reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(16)

        header = QVBoxLayout()
        header.setSpacing(10)
        title = QLabel("Profiles")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Imports stay untouched; a generated copy runs.")
        subtitle.setObjectName("PageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)

        self._update_all_button = QPushButton("Update all")
        self._update_all_button.setToolTip("Refresh every subscription that is due")
        self._update_all_button.clicked.connect(self._update_all)
        self._import_button = QPushButton("Import YAML…")
        self._import_button.clicked.connect(self._import_file)
        self._subscribe_button = QPushButton("Add subscription…")
        self._subscribe_button.clicked.connect(self._add_subscription)
        self._qr_button = QPushButton("Import QR…")
        self._qr_button.clicked.connect(self._import_qr)
        actions.addWidget(self._update_all_button)
        actions.addWidget(self._import_button)
        actions.addWidget(self._qr_button)
        actions.addWidget(self._subscribe_button)
        header.addLayout(actions)
        root.addLayout(header)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        enable_smooth_scroll(self._list)
        self._list.currentRowChanged.connect(self._on_selection)
        self._list.itemDoubleClicked.connect(lambda _i: self._activate())
        root.addWidget(self._list, 1)

        self._details = QLabel("No profile selected.")
        self._details.setObjectName("Hint")
        self._details.setWordWrap(True)
        root.addWidget(self._details)

        self._rule_hint = QLabel("")
        self._rule_hint.setObjectName("Hint")
        self._rule_hint.setWordWrap(True)
        root.addWidget(self._rule_hint)

        actions = QHBoxLayout()
        self._activate_button = QPushButton("Use this profile")
        self._activate_button.setObjectName("Primary")
        self._activate_button.clicked.connect(self._activate)
        self._refresh_button = QPushButton("Update subscription")
        self._refresh_button.clicked.connect(self._refresh)
        self._delete_button = QPushButton("Delete")
        self._delete_button.setObjectName("Danger")
        self._delete_button.clicked.connect(self._delete)
        actions.addWidget(self._activate_button)
        actions.addWidget(self._refresh_button)
        actions.addStretch(1)
        actions.addWidget(self._delete_button)
        root.addLayout(actions)

    # -- data --------------------------------------------------------------
    def _reload(self) -> None:
        current = self._services.profiles.active_id
        selected_id = self._selected_profile().id if self._selected_profile() else ""
        self._list.blockSignals(True)
        self._list.clear()
        for profile in self._services.profiles.profiles:
            marker = "● " if profile.id == current else "   "
            label = f"{marker}{profile.name}"
            sub = (
                f"{profile.kind.label} · {self._count(profile.proxy_count, 'proxy', 'proxies')} · "
                f"{self._count(profile.rule_count, 'rule', 'rules')} · "
                f"updated {self._when(profile.updated_at)}"
            )
            item = QListWidgetItem(f"{label}\n{sub}")
            item.setData(Qt.ItemDataRole.UserRole, profile.id)
            self._list.addItem(item)
            if profile.id == selected_id:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count():
            self._list.setCurrentRow(0)
        self._on_selection(self._list.currentRow())

    @staticmethod
    def _count(value: int, singular: str, plural: str) -> str:
        return f"{value} {singular if value == 1 else plural}"

    @staticmethod
    def _when(timestamp: float) -> str:
        if not timestamp:
            return "never"
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))

    def _selected_profile(self) -> Profile | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return self._services.profiles.get(str(item.data(Qt.ItemDataRole.UserRole)))

    def _on_selection(self, _row: int) -> None:
        profile = self._selected_profile()
        if profile is None:
            self._details.setText("No profile selected.")
            self._activate_button.setEnabled(False)
            self._refresh_button.setEnabled(False)
            self._delete_button.setEnabled(False)
            return
        active = profile.id == self._services.profiles.active_id
        lines = [
            f"<b>{profile.name}</b> · {profile.kind.label}"
            + (" · <b>active</b>" if active else ""),
            f"{self._count(profile.proxy_count, 'proxy', 'proxies')} · "
            f"{self._count(profile.group_count, 'group', 'groups')} · "
            f"{self._count(profile.rule_count, 'rule', 'rules')} · "
            f"{profile.size / 1024:.1f} KB · updated {self._when(profile.updated_at)}",
        ]
        if profile.url:
            lines.append(f"Source: {redact_url(profile.url)}")
        if profile.note:
            lines.append(f"Notes: {profile.note}")
        self._details.setText("<br>".join(lines))
        self._rule_hint.setText(self._describe_rules(profile))
        self._activate_button.setEnabled(not active)
        self._refresh_button.setEnabled(profile.kind is ProfileKind.SUBSCRIPTION)
        self._delete_button.setEnabled(True)

    def _describe_rules(self, profile: Profile) -> str:
        """Run the rule checker on the stored file, so problems show before Connect."""
        try:
            data = load_yaml_file(self._services.profiles.profile_path(profile.id))
        except Exception as exc:  # noqa: BLE001 - display only
            return f"Rule check unavailable: {exc}"
        analysis = analyze_rules(data)
        head = f"Rule check: {analysis.summary()}"
        if not analysis.issues:
            return head
        problems = analysis.messages(limit=3)
        more = len(analysis.issues) - len(problems)
        text = head + "\n" + "\n".join(problems)
        if more > 0:
            text += f"\n(+{more} more, see Logs after connecting)"
        return text

    # -- subscription updates ---------------------------------------------
    def _update_all(self) -> None:
        if not self._services.updates.update_all(force=True):
            self._details.setText(
                "Nothing to update (no subscription profiles), or an update is already running."
            )

    def _on_update_started(self) -> None:
        self._update_all_button.setEnabled(False)
        self._update_all_button.setText("Updating…")
        self._details.setText("Updating subscriptions…")

    def _on_update_finished(self, updated: int, failed: int) -> None:
        self._update_all_button.setEnabled(True)
        self._update_all_button.setText("Update all")
        self._details.setText(f"Subscription update finished: {updated} updated, {failed} failed.")

    def _on_update_failed(self, name: str, message: str) -> None:
        self._details.setText(f"Update failed for {name}: {message}")

    def _on_active_updated(self, profile: object) -> None:
        name = getattr(profile, "name", "the active profile")
        if self._services.connection.is_connected:
            self._details.setText(
                f"{name} was updated. Disconnect and connect again to apply the new configuration."
            )

    # -- actions -----------------------------------------------------------
    def _import_file(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Import a Mihomo profile", "", "YAML files (*.yaml *.yml);;All files (*)"
        )
        if not path:
            return
        self._import_button.setEnabled(False)
        self._services.runner.submit(
            self._services.profiles.import_file,
            args=(Path(path),),
            on_success=lambda profile: self._after_import(profile),
            on_error=self._show_error,
            on_finished=lambda: self._import_button.setEnabled(True),
        )

    def _import_qr(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Import a QR code",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)",
        )
        if not path:
            return
        self._qr_button.setEnabled(False)

        def work() -> tuple[str, str]:
            text = qr.decode_image(Path(path))
            return qr.classify(text)

        def decoded(result: object) -> None:
            kind, payload = result  # type: ignore[misc]
            if kind == "url":
                self._services.runner.submit(
                    self._services.profiles.import_subscription,
                    args=(payload,),
                    on_success=self._after_import,
                    on_error=self._show_error,
                    on_finished=lambda: self._qr_button.setEnabled(True),
                )
            else:
                self._services.runner.submit(
                    self._services.profiles.import_text,
                    kwargs={"text": payload, "name": "QR import"},
                    on_success=self._after_import,
                    on_error=self._show_error,
                    on_finished=lambda: self._qr_button.setEnabled(True),
                )

        def failed(message: str) -> None:
            self._qr_button.setEnabled(True)
            self._show_error(message)

        self._services.runner.submit(work, on_success=decoded, on_error=failed)

    def _add_subscription(self) -> None:
        url, ok = QInputDialog.getText(
            self, "Add subscription", "Subscription URL (http:// or https://):"
        )
        if not ok or not url.strip():
            return
        self._subscribe_button.setEnabled(False)
        self._services.runner.submit(
            self._services.profiles.import_subscription,
            args=(url.strip(),),
            on_success=lambda profile: self._after_import(profile),
            on_error=self._show_error,
            on_finished=lambda: self._subscribe_button.setEnabled(True),
        )

    def _after_import(self, profile: object) -> None:
        if isinstance(profile, Profile):
            self._details.setText(f"Imported <b>{profile.name}</b>.")
            self._reload()
            self._select(profile.id)

    def _select(self, profile_id: str) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item and item.data(Qt.ItemDataRole.UserRole) == profile_id:
                self._list.setCurrentRow(row)
                return

    def _activate(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        if self._services.connection.state in (
            ConnectionState.CONNECTED,
            ConnectionState.STARTING,
        ):
            QMessageBox.information(
                self,
                "Disconnect first",
                "Disconnect before switching profiles so the running core is not reloaded mid-session.",
            )
            return
        try:
            self._services.profiles.set_active(profile.id)
            self._services.settings.update(last_profile_id=profile.id)
        except Exception as exc:  # noqa: BLE001
            self._show_error(str(exc))
            return
        self._details.setText(f"<b>{profile.name}</b> is now the active profile.")

    def _refresh(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        self._refresh_button.setEnabled(False)
        self._services.runner.submit(
            self._services.profiles.refresh,
            args=(profile.id,),
            on_success=lambda p: self._details.setText(
                f"Updated <b>{p.name}</b>. The previous file was kept as previous.yaml."
            ),
            on_error=self._show_error,
            on_finished=lambda: self._refresh_button.setEnabled(True),
        )

    def _delete(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete profile",
            f"Delete '{profile.name}'? The imported file will be removed from this app.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._services.profiles.delete(profile.id)
        self._reload()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Profile error", message)

    def _on_state(self, state: ConnectionState) -> None:
        busy = state in (ConnectionState.CONNECTED, ConnectionState.STARTING)
        self._activate_button.setEnabled(busy is False and self._selected_profile() is not None)
