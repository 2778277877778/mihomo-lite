"""Profile list: import a local YAML, add a subscription, switch and refresh."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from mihomo_lite.config.loader import load_yaml_file
from mihomo_lite.config.rules import analyze_rules
from mihomo_lite.core import qr
from mihomo_lite.core.services import Services
from mihomo_lite.i18n import tr
from mihomo_lite.models.app_state import ConnectionState
from mihomo_lite.models.profile import Profile, ProfileKind
from mihomo_lite.ui.widgets.smooth_scroll import enable_smooth_scroll
from mihomo_lite.utils.logger import redact_url


class ProfileCard(QFrame):
    """One profile rendered as a clickable glass card."""

    clicked = Signal(str)
    activated = Signal(str)

    def __init__(
        self,
        profile: Profile,
        *,
        active: bool,
        selected: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.profile_id = profile.id
        self.setObjectName("ProfileCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("active", "true" if active else "false")
        self.setProperty("selected", "true" if selected else "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        name = QLabel(profile.name)
        name.setObjectName("ProfileName")
        name.setWordWrap(True)
        top.addWidget(name, 1)
        kind = QLabel(tr(profile.kind.label))
        kind.setObjectName("ProfileBadge")
        top.addWidget(kind, 0, Qt.AlignmentFlag.AlignTop)
        if active:
            badge = QLabel(tr("Active"))
            badge.setObjectName("ProfileBadgeActive")
            top.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        meta = QLabel(
            f"{profile.proxy_count} {tr('nodes')} · "
            f"{profile.group_count} {tr('groups')} · "
            f"{profile.rule_count} {tr('rules')} · "
            f"{profile.size / 1024:.1f} KB"
        )
        meta.setObjectName("ProfileMeta")
        layout.addWidget(meta)

        source = tr("Updated") + " " + _when(profile.updated_at)
        if profile.url:
            link = redact_url(profile.url)
            if len(link) > 72:
                link = link[:69] + "…"
            source += " · " + tr("Source") + ": " + link
        source_label = QLabel(source)
        source_label.setObjectName("ProfileMeta")
        layout.addWidget(source_label)

        if profile.note:
            warning = QLabel("⚠")
            warning.setObjectName("ProfileWarning")
            warning.setToolTip(profile.note)
            top.addWidget(warning, 0, Qt.AlignmentFlag.AlignTop)

        # Let clicks reach the card itself rather than being swallowed by labels.
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_selected(self, selected: bool) -> None:
        if self.property("selected") == ("true" if selected else "false"):
            return
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.profile_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.profile_id)
        super().mouseDoubleClickEvent(event)


class ProfilePage(QWidget):
    def __init__(self, services: Services, parent=None) -> None:
        super().__init__(parent)
        self._services = services
        self._cards: dict[str, ProfileCard] = {}
        self._selected_id = ""
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
        root.setSpacing(14)

        header = QVBoxLayout()
        header.setSpacing(10)
        title = QLabel("Profiles")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Imports stay untouched; a generated copy runs.")
        subtitle.setObjectName("PageSubtitle")
        self._summary = QLabel("")
        self._summary.setObjectName("Hint")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addWidget(self._summary)

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

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        enable_smooth_scroll(self._scroll)
        self._cards_host = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 6, 0)
        self._cards_layout.setSpacing(10)
        self._scroll.setWidget(self._cards_host)
        root.addWidget(self._scroll, 1)

        details = QFrame()
        details.setObjectName("Card")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(16, 12, 16, 12)
        details_layout.setSpacing(6)
        details_title = QLabel("Profile details")
        details_title.setObjectName("MetricLabel")
        details_layout.addWidget(details_title)
        self._details = QLabel("No profile selected.")
        self._details.setObjectName("Hint")
        self._details.setWordWrap(True)
        details_layout.addWidget(self._details)
        rule_title = QLabel("Rule check")
        rule_title.setObjectName("MetricLabel")
        details_layout.addWidget(rule_title)
        self._rule_hint = QLabel("")
        self._rule_hint.setObjectName("Hint")
        self._rule_hint.setWordWrap(True)
        details_layout.addWidget(self._rule_hint)
        root.addWidget(details)

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
        profiles = self._services.profiles.profiles
        current = self._services.profiles.active_id
        if self._services.profiles.get(self._selected_id) is None:
            self._selected_id = current or (profiles[0].id if profiles else "")

        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._cards.clear()

        for profile in profiles:
            card = ProfileCard(
                profile,
                active=profile.id == current,
                selected=profile.id == self._selected_id,
            )
            card.clicked.connect(self._select_profile)
            card.activated.connect(self._activate_profile)
            self._cards[profile.id] = card
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch(1)

        active_count = sum(1 for profile in profiles if profile.id == current)
        self._summary.setText(
            tr("{count} profiles · {active} active").format(
                count=len(profiles), active=active_count
            )
            if profiles
            else tr("No profiles yet. Import a YAML file or add a subscription.")
        )
        self._select_profile(self._selected_id)

    @staticmethod
    def _count(value: int, singular: str, plural: str) -> str:
        return f"{value} {singular if value == 1 else plural}"

    def _selected_profile(self) -> Profile | None:
        if not self._selected_id:
            return None
        return self._services.profiles.get(self._selected_id)

    def _select_profile(self, profile_id: str) -> None:
        if self._services.profiles.get(profile_id) is None:
            profile_id = ""
        self._selected_id = profile_id
        for card in self._cards.values():
            card.set_selected(card.profile_id == profile_id)
        self._update_details()
        selected = self._cards.get(profile_id)
        if selected is not None:
            self._scroll.ensureWidgetVisible(selected, 24, 24)

    def _update_details(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self._details.setText(tr("No profile selected."))
            self._rule_hint.setText("")
            self._activate_button.setEnabled(False)
            self._refresh_button.setEnabled(False)
            self._delete_button.setEnabled(False)
            return
        active = profile.id == self._services.profiles.active_id
        lines = [
            f"<b>{profile.name}</b> · {tr(profile.kind.label)}"
            + (f" · <b>{tr('Active')}</b>" if active else ""),
            f"{self._count(profile.proxy_count, 'proxy', 'proxies')} · "
            f"{self._count(profile.group_count, 'group', 'groups')} · "
            f"{self._count(profile.rule_count, 'rule', 'rules')} · "
            f"{profile.size / 1024:.1f} KB · {tr('Updated')} {_when(profile.updated_at)}",
        ]
        if profile.url:
            lines.append(f"{tr('Source')}: {redact_url(profile.url)}")
        if profile.note:
            note = profile.note
            if len(note) > 180:
                note = note[:177] + "…"
            lines.append(f"{tr('Notes')}: {note}")
        self._details.setText("<br>".join(lines))
        rule_text = self._describe_rules(profile)
        self._rule_hint.setText(rule_text.splitlines()[0] if rule_text else "")
        self._rule_hint.setToolTip(rule_text)
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
            self._select_profile(profile.id)

    def _activate_profile(self, profile_id: str) -> None:
        self._select_profile(profile_id)
        self._activate()

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
        self._selected_id = ""
        self._reload()

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Profile error", message)

    def _on_state(self, state: ConnectionState) -> None:
        busy = state in (ConnectionState.CONNECTED, ConnectionState.STARTING)
        self._activate_button.setEnabled(busy is False and self._selected_profile() is not None)


def _when(timestamp: float) -> str:
    if not timestamp:
        return "never"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
