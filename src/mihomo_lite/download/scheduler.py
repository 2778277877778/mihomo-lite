"""Pure in-memory scheduling helpers: segment pool, node pool, throttling.

Nothing in this module touches the network, which keeps the tricky booking
logic directly unit-testable.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from mihomo_lite.download.types import NodeRoute, NodeState

log = logging.getLogger(__name__)

DEFAULT_MIN_SPLIT = 1024 * 1024
_THROTTLE_STATUSES = (403, 429)


@dataclass
class Segment:
    """A byte range [start, end) with its progress."""

    start: int
    end: int
    done: int = 0
    attempts: int = 0
    node: str = ""
    worker_id: int = -1

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def remaining(self) -> int:
        return max(0, self.length - self.done)

    @property
    def position(self) -> int:
        return self.start + min(self.done, self.length)

    @property
    def complete(self) -> bool:
        return self.remaining <= 0

    def to_state(self) -> tuple[int, int, int, int, str]:
        return (self.start, self.end, self.done, self.attempts, self.node)


class SegmentPool:
    """Splits the byte range and hands out work to worker threads.

    The invariant is that at every instant the pool's segments exactly cover
    [0, total) without overlap, even while segments are split under load.
    """

    def __init__(
        self,
        total: int,
        thread_count: int,
        min_split: int = DEFAULT_MIN_SPLIT,
        *,
        segments: Sequence[Segment] | None = None,
    ) -> None:
        self._total = max(0, int(total))
        self._min_split = max(1, int(min_split))
        self._lock = threading.Lock()
        if segments:
            self._segments = [replace(segment) for segment in segments]
        else:
            self._segments = self._initial_segments(thread_count)

    @property
    def total(self) -> int:
        return self._total

    def _initial_segments(self, thread_count: int) -> list[Segment]:
        if self._total <= 0:
            return []
        count = max(1, min(int(thread_count), self._total))
        base_size, remainder = divmod(self._total, count)
        segments: list[Segment] = []
        start = 0
        for index in range(count):
            length = base_size + (1 if index < remainder else 0)
            if length <= 0:
                continue
            segments.append(Segment(start=start, end=start + length))
            start += length
        return segments

    def next_task(self, worker_id: int, node_name: str) -> Segment | None:
        """Claim a free segment, or split the longest remaining segment in two."""
        with self._lock:
            for segment in self._segments:
                if segment.worker_id == -1 and segment.remaining > 0:
                    segment.worker_id = worker_id
                    segment.node = node_name
                    return segment
            target = self._longest_splittable(worker_id)
            if target is None:
                return None
            position = target.start + target.done
            remaining = target.end - position
            midpoint = position + remaining // 2
            new_segment = Segment(
                start=midpoint,
                end=target.end,
                node=node_name,
                worker_id=worker_id,
            )
            target.end = midpoint
            self._segments.append(new_segment)
            return new_segment

    def _longest_splittable(self, worker_id: int) -> Segment | None:
        best: Segment | None = None
        for segment in self._segments:
            if segment.worker_id == worker_id or segment.remaining <= self._min_split:
                continue
            if best is None or segment.remaining > best.remaining:
                best = segment
        return best

    def add_progress(self, segment: Segment, count: int) -> None:
        with self._lock:
            segment.done = min(segment.length, segment.done + max(0, count))

    def mark_done(self, segment: Segment, bytes_done: int | None = None) -> None:
        """Record cumulative bytes completed for the segment and release it."""
        with self._lock:
            if bytes_done is None:
                segment.done = segment.length
            else:
                segment.done = max(segment.done, min(segment.length, int(bytes_done)))
            segment.worker_id = -1

    def requeue(self, segment: Segment) -> None:
        """Return a partially finished segment to the pool."""
        with self._lock:
            segment.worker_id = -1

    def remaining(self) -> int:
        with self._lock:
            return sum(segment.remaining for segment in self._segments)

    def snapshot(self) -> tuple[Segment, ...]:
        with self._lock:
            return tuple(replace(segment) for segment in self._segments)

    def is_complete(self) -> bool:
        return self.remaining() == 0


class NodePool:
    """Tracks healthy routes, worker assignments and per-node statistics."""

    def __init__(
        self,
        routes: Sequence[NodeRoute],
        fallback_name: str = "single",
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._routes = tuple(routes)
        self._fallback_name = fallback_name
        self._clock = clock
        self._lock = threading.Lock()
        now = clock()
        self._healthy: dict[str, bool] = {route.name: True for route in self._routes}
        self._reasons: dict[str, str] = {}
        self._downloaded: dict[str, int] = dict.fromkeys(self._healthy, 0)
        self._sampled_at: dict[str, float] = dict.fromkeys(self._healthy, now)
        self._sampled_bytes: dict[str, int] = dict.fromkeys(self._healthy, 0)
        self._speeds: dict[str, float] = dict.fromkeys(self._healthy, 0.0)
        self._workers: dict[str, set[int]] = {route.name: set() for route in self._routes}
        self._routes_by_name = {route.name: route for route in self._routes}

    @property
    def fallback_name(self) -> str:
        return self._fallback_name

    def route(self, name: str) -> NodeRoute | None:
        return self._routes_by_name.get(name)

    def next_available(self, worker_id: int) -> NodeRoute | None:
        """Return a healthy route for the worker, preferring its current one."""
        with self._lock:
            healthy = [route for route in self._routes if self._healthy.get(route.name)]
            if not healthy:
                return None
            for name, workers in self._workers.items():
                if worker_id in workers and self._healthy.get(name):
                    return self._routes_by_name[name]
            chosen = min(healthy, key=lambda route: len(self._workers[route.name]))
            for workers in self._workers.values():
                workers.discard(worker_id)
            self._workers[chosen.name].add(worker_id)
            return chosen

    def mark_failed(self, name: str, reason: str = "") -> None:
        with self._lock:
            if name not in self._healthy:
                return
            self._healthy[name] = False
            self._reasons[name] = reason
            self._workers[name].clear()

    def is_healthy(self, name: str) -> bool:
        with self._lock:
            return self._healthy.get(name, False)

    @property
    def healthy_nodes(self) -> tuple[NodeRoute, ...]:
        with self._lock:
            return tuple(route for route in self._routes if self._healthy.get(route.name))

    def record_bytes(self, name: str, count: int) -> None:
        with self._lock:
            if name in self._downloaded:
                self._downloaded[name] += max(0, count)

    def downloaded(self, name: str) -> int:
        with self._lock:
            return self._downloaded.get(name, 0)

    def refresh_speeds(self) -> dict[str, float]:
        with self._lock:
            now = self._clock()
            for name in self._downloaded:
                elapsed = now - self._sampled_at[name]
                if elapsed <= 1e-6:
                    continue
                delta = self._downloaded[name] - self._sampled_bytes[name]
                self._speeds[name] = max(0.0, delta / elapsed)
                self._sampled_at[name] = now
                self._sampled_bytes[name] = self._downloaded[name]
            return dict(self._speeds)

    def states(self) -> tuple[NodeState, ...]:
        with self._lock:
            return tuple(
                NodeState(
                    name=route.name,
                    state="ok" if self._healthy.get(route.name) else "error",
                    downloaded=self._downloaded[route.name],
                    speed=self._speeds[route.name],
                    message=self._reasons.get(route.name, ""),
                )
                for route in self._routes
            )


class ThrottlePolicy:
    """Decides when HTTP 403/429 responses should force a single node."""

    def __init__(self, *, node_limit: int = 2, strike_limit: int = 3) -> None:
        if node_limit < 1 or strike_limit < 1:
            raise ValueError("throttle limits must be positive")
        self._node_limit = node_limit
        self._strike_limit = strike_limit
        self._lock = threading.Lock()
        self._streaks: dict[str, int] = {}
        self._seen: set[str] = set()

    def record(self, node_name: str, status: int) -> bool:
        """Record a response status; True when it counts as throttling."""
        if status not in _THROTTLE_STATUSES:
            return False
        with self._lock:
            self._seen.add(node_name)
            self._streaks[node_name] = self._streaks.get(node_name, 0) + 1
        return True

    def record_success(self, node_name: str) -> None:
        with self._lock:
            if node_name in self._streaks:
                self._streaks[node_name] = 0

    @property
    def throttled_nodes(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._seen))

    def should_degrade(self) -> bool:
        with self._lock:
            if len(self._seen) >= self._node_limit:
                return True
            return any(streak >= self._strike_limit for streak in self._streaks.values())

    def reason(self) -> str:
        with self._lock:
            if len(self._seen) >= self._node_limit:
                return f"{len(self._seen)} nodes rejected range requests with HTTP 403/429"
            for name, streak in self._streaks.items():
                if streak >= self._strike_limit:
                    return f"node {name} returned HTTP 403/429 {streak} times in a row"
        return ""

    def __repr__(self) -> str:
        return f"ThrottlePolicy(nodes={self.throttled_nodes!r})"
