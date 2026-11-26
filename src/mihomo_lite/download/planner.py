"""Decide whether one download can use multiple connections."""

from __future__ import annotations

from dataclasses import dataclass

from mihomo_lite.download.types import DownloadOptions, HeadInfo

MIN_THREADS = 4
MAX_THREADS = 16

_MIB = 1024 * 1024
_SMALL_LIMIT = 16 * _MIB
_MEDIUM_LIMIT = 64 * _MIB
_LARGE_LIMIT = 256 * _MIB


@dataclass(frozen=True)
class DownloadPlan:
    """How the engine should execute one download."""

    total: int
    supports_ranges: bool
    thread_count: int
    reason: str = ""


def auto_thread_count(total_size: int, requested: int = 0) -> int:
    """Return 4..16 worker threads for a file of total_size bytes.

    An explicit requested value inside 4..16 is honoured as-is; otherwise the
    count is derived from the file size.
    """
    if MIN_THREADS <= requested <= MAX_THREADS:
        return requested
    if total_size <= 0:
        return MIN_THREADS
    if total_size < _SMALL_LIMIT:
        return 4
    if total_size < _MEDIUM_LIMIT:
        return 8
    if total_size < _LARGE_LIMIT:
        return 12
    return MAX_THREADS


def plan(head: HeadInfo, options: DownloadOptions) -> DownloadPlan:
    """Build the execution plan for a probe result."""
    total = max(0, head.content_length)
    if not options.multithreaded:
        return DownloadPlan(total, bool(head.accept_ranges), 1, "multithreaded downloads are disabled")
    if not head.accept_ranges:
        return DownloadPlan(total, False, 1, "server does not advertise byte-range support")
    if total <= 0:
        return DownloadPlan(0, False, 1, "download size is unknown")
    thread_count = max(1, min(MAX_THREADS, auto_thread_count(total, options.thread_count)))
    if thread_count <= 1:
        return DownloadPlan(total, True, 1, "a single connection was requested")
    return DownloadPlan(total, True, thread_count, "")
