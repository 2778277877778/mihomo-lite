"""Pure-Python download engine for mihomo-lite.

This package must stay free of PySide6 imports: the GUI layer runs it on
worker threads only.
"""

from __future__ import annotations

from mihomo_lite.download.engine import DownloadEngine
from mihomo_lite.download.planner import DownloadPlan, auto_thread_count
from mihomo_lite.download.resume import DownloadState, SegmentState, StateStore
from mihomo_lite.download.scheduler import NodePool, Segment, SegmentPool, ThrottlePolicy
from mihomo_lite.download.transport import HttpxTransport, Transport
from mihomo_lite.download.types import (
    DownloadError,
    DownloadOptions,
    DownloadResult,
    DownloadSnapshot,
    HeadInfo,
    HttpStatusError,
    NodeFailed,
    NodeRoute,
    NodeState,
    RangeNotSupported,
)

__all__ = [
    "DownloadEngine",
    "DownloadError",
    "DownloadOptions",
    "DownloadPlan",
    "DownloadResult",
    "DownloadSnapshot",
    "DownloadState",
    "HeadInfo",
    "HttpStatusError",
    "HttpxTransport",
    "NodeFailed",
    "NodePool",
    "NodeRoute",
    "NodeState",
    "RangeNotSupported",
    "Segment",
    "SegmentPool",
    "SegmentState",
    "StateStore",
    "ThrottlePolicy",
    "Transport",
    "auto_thread_count",
]
