"""A tiny service container passed to every page (no global state)."""

from __future__ import annotations

from dataclasses import dataclass

from mihomo_lite.core.connection_manager import ConnectionManager
from mihomo_lite.core.profile_manager import ProfileManager
from mihomo_lite.core.proxy_manager import ProxyManager
from mihomo_lite.core.state_manager import SettingsStore
from mihomo_lite.core.traffic_monitor import TrafficMonitor
from mihomo_lite.core.traffic_stats import TrafficStats
from mihomo_lite.core.update_scheduler import UpdateScheduler
from mihomo_lite.mihomo.core_manager import CoreManager
from mihomo_lite.system.paths import AppPaths
from mihomo_lite.utils.tasks import TaskRunner


@dataclass
class Services:
    paths: AppPaths
    settings: SettingsStore
    profiles: ProfileManager
    connection: ConnectionManager
    proxy: ProxyManager
    core: CoreManager
    runner: TaskRunner
    traffic: TrafficMonitor
    stats: TrafficStats
    updates: UpdateScheduler
