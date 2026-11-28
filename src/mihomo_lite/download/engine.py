"""Multithreaded, multi-node, resumable download engine.

The engine is deliberately pure Python: standard library plus httpx through the
transport layer. It never imports PySide6 and never talks to the mihomo
controller API; every request goes through a loopback proxy port.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import BinaryIO

from mihomo_lite.download.planner import DownloadPlan
from mihomo_lite.download.planner import plan as build_plan
from mihomo_lite.download.resume import (
    DownloadState,
    SegmentState,
    StateStore,
    default_state_path,
    new_state,
    prepare_target,
    state_matches,
)
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

log = logging.getLogger(__name__)

_BASE_BACKOFF = 0.25
_MAX_BACKOFF = 8.0
_RANGE_WINDOW = 1024 * 1024
_POLL_INTERVAL = 0.05
_THROTTLE_STATUSES = (403, 429)
_SINGLE_NODE = "single"
_FALLBACK_NODE = "single"


class _Cancelled(Exception):
    """Internal signal used to unwind workers quickly."""


@dataclass
class _Run:
    """Per-call context handed to helpers."""

    options: DownloadOptions
    transport: Transport
    emit: Callable[[DownloadSnapshot], None]
    stop: threading.Event
    store: StateStore
    clock: Callable[[], float]
    sleep: Callable[[float], None]
    window: int
    last_emit: float = float("-inf")


class _Coordinator:
    """Shared abort/degrade state for the worker threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._degraded = False
        self._reason = ""
        self._error: DownloadError | None = None

    @property
    def degraded(self) -> bool:
        with self._lock:
            return self._degraded

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def error(self) -> DownloadError | None:
        with self._lock:
            return self._error

    def trigger_degrade(self, reason: str) -> None:
        with self._lock:
            if not self._degraded:
                self._degraded = True
                self._reason = reason

    def fail(self, error: DownloadError) -> None:
        with self._lock:
            if self._error is None:
                self._error = error

    def should_abort(self) -> bool:
        with self._lock:
            return self._degraded or self._error is not None


class _Meter:
    """Computes an overall transfer speed sample."""

    def __init__(self, clock: Callable[[], float], downloaded: int = 0) -> None:
        self._clock = clock
        self._downloaded = downloaded
        self._last_time = clock()
        self._last_downloaded = downloaded
        self.speed = 0.0

    def update(self, downloaded: int) -> float:
        now = self._clock()
        elapsed = now - self._last_time
        if elapsed >= _POLL_INTERVAL:
            self.speed = max(0.0, (downloaded - self._last_downloaded) / elapsed)
            self._last_time = now
            self._last_downloaded = downloaded
        return self.speed


class DownloadEngine:
    """Downloads one URL into a preallocated file, optionally in parallel."""

    def __init__(
        self,
        transport_factory: Callable[[], Transport] = HttpxTransport,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport_factory = transport_factory
        self._clock = clock
        self._sleep = sleep

    def run(
        self,
        options: DownloadOptions,
        on_snapshot: Callable[[DownloadSnapshot], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> DownloadResult:
        """Execute one download and return its result (never raises).

        The progress callback is invoked from the calling thread for the
        single-connection path and from the coordinating thread for the
        parallel path. Cancellation is cooperative; the saved state file is
        written before the result is returned.
        """
        emit = on_snapshot if on_snapshot is not None else _ignore_snapshot
        stop = cancel if cancel is not None else threading.Event()
        context: _Run | None = None
        try:
            context = self._new_run(options, emit, stop)
            head = self._probe_head(context)
            plan = build_plan(head, options)
            fallback_reason = ""
            multi = (
                options.multithreaded
                and plan.supports_ranges
                and plan.thread_count > 1
                and plan.total > 0
            )
            if options.multithreaded and not multi:
                fallback_reason = plan.reason
                log.info(
                    "using a single connection for %s: %s",
                    options.target.name,
                    fallback_reason,
                )
            if multi:
                return self._download_multi(context, head, plan)
            return self._download_single(context, head, fallback_reason)
        except _Cancelled:
            return DownloadResult(
                target=options.target,
                total=0,
                downloaded=0,
                ok=False,
                error="cancelled",
            )
        except (DownloadError, OSError) as exc:
            log.warning("download of %s failed: %s", options.target.name, exc)
            return DownloadResult(
                target=options.target,
                total=0,
                downloaded=0,
                ok=False,
                error=str(exc) or "download failed",
            )
        finally:
            if context is not None:
                close = getattr(context.transport, "close", None)
                if callable(close):
                    close()

    # -- probing -----------------------------------------------------------
    def _new_run(
        self,
        options: DownloadOptions,
        emit: Callable[[DownloadSnapshot], None],
        stop: threading.Event,
    ) -> _Run:
        state_path = options.state_path or default_state_path(options.target)
        return _Run(
            options=options,
            transport=self._transport_factory(),
            emit=emit,
            stop=stop,
            store=StateStore(state_path),
            clock=self._clock,
            sleep=self._sleep,
            window=max(_RANGE_WINDOW, options.chunk_size),
        )

    def _probe_head(self, context: _Run) -> HeadInfo:
        options = context.options
        attempts = 0
        while True:
            try:
                return context.transport.head(options.url, options.proxy_port)
            except RangeNotSupported as exc:
                log.info(
                    "HEAD is unusable for %s (%s); falling back to a plain GET",
                    options.target.name,
                    exc,
                )
                return _unknown_head(options.url)
            except HttpStatusError as exc:
                if exc.status in (403, 405):
                    log.info(
                        "HEAD returned HTTP %d for %s; falling back to a plain GET",
                        exc.status,
                        options.target.name,
                    )
                    return _unknown_head(options.url)
                raise
            except NodeFailed as exc:
                attempts += 1
                if attempts > max(1, options.max_retries):
                    raise DownloadError(f"HEAD probe failed: {exc}") from exc
                context.sleep(_backoff_delay(attempts))

    # -- single connection -------------------------------------------------
    def _download_single(
        self,
        context: _Run,
        head: HeadInfo,
        fallback_reason: str = "",
    ) -> DownloadResult:
        options = context.options
        target = options.target
        total = head.content_length
        url = head.final_url or head.url
        if not head.accept_ranges or total < 0:
            return self._download_full(context, head, fallback_reason)
        if total == 0:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"")
            context.store.remove()
            snapshot = DownloadSnapshot(
                total=0,
                downloaded=0,
                speed=0.0,
                eta_seconds=0.0,
                threads=1,
                done=True,
            )
            self._notify(context, snapshot, force=True)
            return DownloadResult(
                target=target,
                total=0,
                downloaded=0,
                ok=True,
                fallback_reason=fallback_reason,
            )
        if total < 0:
            raise DownloadError("the server did not report a Content-Length")

        state = context.store.load()
        resumed_bytes = 0
        if state_matches(state, head):
            candidate = _single_segment_done(state, total)
            if candidate is not None:
                resumed_bytes = candidate
        if state is None or not state_matches(state, head):
            state = new_state(head)
        state.segments = [SegmentState(start=0, end=total, done=resumed_bytes)]
        state.completed = False

        meter = _Meter(context.clock, resumed_bytes)
        self._notify(
            context,
            self._single_snapshot(context, total, resumed_bytes, meter),
            state,
        )

        pos = resumed_bytes
        cancelled = False
        attempts = 0
        with prepare_target(target, total) as handle:
            while pos < total and not context.stop.is_set():
                start_pos = pos
                request_end = min(total - 1, pos + context.window - 1)
                stream = None
                try:
                    stream = context.transport.get_range(
                        url,
                        options.proxy_port,
                        pos,
                        request_end,
                        etag=head.etag,
                        last_modified=head.last_modified,
                    )
                    for chunk in stream:
                        if context.stop.is_set():
                            cancelled = True
                            break
                        data = chunk[: total - pos]
                        if not data:
                            continue
                        handle.seek(pos)
                        handle.write(data)
                        pos += len(data)
                        attempts = 0
                        state.segments[0].done = pos
                        meter.update(pos)
                        self._notify(
                            context,
                            self._single_snapshot(context, total, pos, meter),
                            state,
                        )
                except (NodeFailed, HttpStatusError) as exc:
                    if context.stop.is_set():
                        cancelled = True
                        break
                    if not _retryable(exc):
                        raise DownloadError(f"range request failed: {exc}") from exc
                    attempts += 1
                    if attempts > max(1, options.max_retries):
                        raise DownloadError(
                            f"giving up after {options.max_retries} retries: {exc}"
                        ) from exc
                    log.debug(
                        "retry %d for %s after %s", attempts, target.name, type(exc).__name__
                    )
                    context.sleep(_backoff_delay(attempts))
                    continue
                finally:
                    if stream is not None:
                        _close_stream(stream)
                if cancelled or context.stop.is_set():
                    cancelled = True
                    break
                if pos == start_pos:
                    attempts += 1
                    if attempts > max(1, options.max_retries):
                        raise DownloadError("server returned no data for the requested range")
                    context.sleep(_backoff_delay(attempts))

        if cancelled or context.stop.is_set():
            _save_state(context, state)
            snapshot = self._single_snapshot(
                context, total, pos, meter, done=False, error="cancelled"
            )
            self._notify(context, snapshot, force=True)
            return DownloadResult(
                target=target,
                total=total,
                downloaded=pos,
                ok=False,
                error="cancelled",
                resumed_bytes=resumed_bytes,
                fallback_reason=fallback_reason,
            )

        if pos != total:
            raise DownloadError(f"download stopped at {pos} of {total} bytes")
        size = target.stat().st_size
        if size != total:
            raise DownloadError(f"target file has {size} bytes, expected {total}")

        state.segments[0].done = total
        state.completed = True
        _save_state(context, state)
        context.store.remove()
        snapshot = self._single_snapshot(context, total, total, meter, done=True)
        self._notify(context, snapshot, force=True)
        return DownloadResult(
            target=target,
            total=total,
            downloaded=total,
            ok=True,
            resumed_bytes=resumed_bytes,
            fallback_reason=fallback_reason,
        )

    def _download_full(
        self,
        context: _Run,
        head: HeadInfo,
        fallback_reason: str = "",
    ) -> DownloadResult:
        """Download the whole body with a plain GET (no byte ranges).

        Used when the server does not support ranges (or HEAD was unusable), so
        this path cannot resume: the target is rewritten from byte zero.
        """
        options = context.options
        target = options.target
        url = head.final_url or head.url
        reported_total = max(0, head.content_length)
        target.parent.mkdir(parents=True, exist_ok=True)
        # A plain GET cannot resume; a stale range state would be misleading.
        context.store.remove()
        meter = _Meter(context.clock, 0)
        attempts = 0
        written = 0
        cancelled = False
        self._notify(
            context,
            self._full_snapshot(context, reported_total, 0, meter),
        )
        with open(target, "w+b") as handle:
            while True:
                if context.stop.is_set():
                    cancelled = True
                    break
                if written:
                    handle.seek(0)
                    handle.truncate(0)
                    written = 0
                stream = None
                try:
                    stream = context.transport.get_full(url, options.proxy_port)
                    for chunk in stream:
                        if context.stop.is_set():
                            cancelled = True
                            break
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        attempts = 0
                        meter.update(written)
                        self._notify(
                            context,
                            self._full_snapshot(context, reported_total, written, meter),
                        )
                except (NodeFailed, HttpStatusError) as exc:
                    if context.stop.is_set():
                        cancelled = True
                        break
                    if not _retryable(exc):
                        raise DownloadError(f"download failed: {exc}") from exc
                    attempts += 1
                    if attempts > max(1, options.max_retries):
                        raise DownloadError(
                            f"giving up after {options.max_retries} retries: {exc}"
                        ) from exc
                    log.debug(
                        "retry %d for %s after %s",
                        attempts,
                        target.name,
                        type(exc).__name__,
                    )
                    context.sleep(_backoff_delay(attempts))
                    continue
                finally:
                    if stream is not None:
                        _close_stream(stream)
                if cancelled:
                    break
                break
            handle.flush()
            if not cancelled:
                handle.truncate(written)

        if cancelled or context.stop.is_set():
            snapshot = self._full_snapshot(
                context,
                reported_total,
                written,
                meter,
                streamed_total=written,
                done=False,
                error="cancelled",
            )
            self._notify(context, snapshot, force=True)
            return DownloadResult(
                target=target,
                total=written,
                downloaded=written,
                ok=False,
                error="cancelled",
                fallback_reason=fallback_reason,
            )

        if reported_total > 0 and reported_total != written:
            log.info(
                "server sent %d bytes for %s while HEAD reported %d",
                written,
                target.name,
                reported_total,
            )
        snapshot = self._full_snapshot(
            context,
            reported_total,
            written,
            meter,
            streamed_total=written,
            done=True,
        )
        self._notify(context, snapshot, force=True)
        return DownloadResult(
            target=target,
            total=written,
            downloaded=written,
            ok=True,
            fallback_reason=fallback_reason,
        )

    def _full_snapshot(
        self,
        context: _Run,
        reported_total: int,
        downloaded: int,
        meter: _Meter,
        *,
        streamed_total: int | None = None,
        done: bool = False,
        error: str = "",
    ) -> DownloadSnapshot:
        total = streamed_total if streamed_total is not None else max(0, reported_total)
        speed = meter.update(downloaded)
        remaining = max(0, total - downloaded)
        eta = remaining / speed if speed > 1e-6 else 0.0
        node = NodeState(
            name=_SINGLE_NODE,
            state="ok",
            downloaded=downloaded,
            speed=speed,
        )
        return DownloadSnapshot(
            total=total,
            downloaded=downloaded,
            speed=speed,
            eta_seconds=eta,
            threads=1,
            done=done,
            error=error,
            nodes=(node,),
        )

    # -- parallel ----------------------------------------------------------
    def _download_multi(
        self,
        context: _Run,
        head: HeadInfo,
        plan: DownloadPlan,
    ) -> DownloadResult:
        options = context.options
        target = options.target
        total = plan.total
        state = context.store.load()
        resumed_bytes = 0
        initial: list[Segment] = []
        if state is not None and state_matches(state, head) and state.segments:
            candidate = [_segment_from_state(item, total) for item in state.segments]
            candidate = [segment for segment in candidate if segment.end > segment.start]
            if _segments_cover(candidate, total):
                initial = candidate
                resumed_bytes = sum(segment.done for segment in initial)
                log.info(
                    "resuming %s at %d of %d bytes", target.name, resumed_bytes, total
                )
        if not initial:
            state = new_state(head)
        state.completed = False

        preallocation = prepare_target(target, total)
        preallocation.close()

        pool = SegmentPool(total, plan.thread_count, segments=initial or None)
        multi_node = bool(options.multi_node and options.node_routes)
        routes = (
            tuple(options.node_routes)
            if multi_node
            else (NodeRoute(_SINGLE_NODE, options.proxy_port),)
        )
        node_pool = NodePool(routes, fallback_name=_FALLBACK_NODE)
        throttle = ThrottlePolicy()
        coordinator = _Coordinator()
        meter = _Meter(context.clock, resumed_bytes)
        # Keep the planned parallelism even with a single route: several workers
        # may share one node, which is still a multi-connection download.
        worker_count = plan.thread_count if node_pool.healthy_nodes else 0
        if worker_count == 0:
            coordinator.trigger_degrade("no healthy proxy nodes")

        workers: list[threading.Thread] = []
        for worker_id in range(worker_count):
            worker = threading.Thread(
                target=self._worker,
                args=(
                    worker_id,
                    context,
                    pool,
                    node_pool,
                    throttle,
                    coordinator,
                    head,
                    total,
                    multi_node,
                ),
                name=f"mihomo-download-{worker_id}",
                daemon=True,
            )
            workers.append(worker)
            worker.start()

        self._sync_state(state, pool)
        self._notify(
            context,
            self._multi_snapshot(context, total, _pool_downloaded(pool), node_pool, meter, worker_count),
            state,
        )
        while True:
            alive = [worker for worker in workers if worker.is_alive()]
            if not alive:
                break
            alive[0].join(_POLL_INTERVAL)
            self._sync_state(state, pool)
            self._notify(
                context,
                self._multi_snapshot(
                    context, total, _pool_downloaded(pool), node_pool, meter, worker_count
                ),
                state,
            )

        downloaded = _pool_downloaded(pool)
        fallback_used = False
        fallback_reason = ""
        fallback_bytes = 0

        if coordinator.error is not None:
            _save_state(context, state)
            error = str(coordinator.error) or "download failed"
            snapshot = self._multi_snapshot(
                context,
                total,
                downloaded,
                node_pool,
                meter,
                worker_count,
                done=False,
                error=error,
            )
            self._notify(context, snapshot, force=True)
            return DownloadResult(
                target=target,
                total=total,
                downloaded=downloaded,
                ok=False,
                error=error,
                resumed_bytes=resumed_bytes,
            )

        if context.stop.is_set():
            _save_state(context, state)
            snapshot = self._multi_snapshot(
                context,
                total,
                downloaded,
                node_pool,
                meter,
                worker_count,
                done=False,
                error="cancelled",
            )
            self._notify(context, snapshot, force=True)
            return DownloadResult(
                target=target,
                total=total,
                downloaded=downloaded,
                ok=False,
                error="cancelled",
                resumed_bytes=resumed_bytes,
            )

        if coordinator.degraded:
            fallback_used = True
            fallback_reason = coordinator.reason or "too many rejected range requests"
            log.warning("degrading %s to one node: %s", target.name, fallback_reason)
            try:
                self._drain_fallback(
                    context, state, pool, node_pool, meter, head, total, worker_count
                )
            except (DownloadError, OSError) as exc:
                _save_state(context, state)
                error = str(exc) or "fallback download failed"
                snapshot = self._multi_snapshot(
                    context,
                    total,
                    _pool_downloaded(pool),
                    node_pool,
                    meter,
                    worker_count,
                    fallback_used=True,
                    done=False,
                    error=error,
                )
                self._notify(context, snapshot, force=True)
                return DownloadResult(
                    target=target,
                    total=total,
                    downloaded=_pool_downloaded(pool),
                    ok=False,
                    error=error,
                    resumed_bytes=resumed_bytes,
                    fallback_reason=fallback_reason,
                )
            if context.stop.is_set():
                _save_state(context, state)
                snapshot = self._multi_snapshot(
                    context,
                    total,
                    _pool_downloaded(pool),
                    node_pool,
                    meter,
                    worker_count,
                    fallback_used=True,
                    done=False,
                    error="cancelled",
                )
                self._notify(context, snapshot, force=True)
                return DownloadResult(
                    target=target,
                    total=total,
                    downloaded=_pool_downloaded(pool),
                    ok=False,
                    error="cancelled",
                    resumed_bytes=resumed_bytes,
                    fallback_reason=fallback_reason,
                )
            downloaded = _pool_downloaded(pool)
            fallback_bytes = downloaded

        if not pool.is_complete():
            _save_state(context, state)
            return DownloadResult(
                target=target,
                total=total,
                downloaded=_pool_downloaded(pool),
                ok=False,
                error="download did not complete",
                resumed_bytes=resumed_bytes,
                fallback_reason=fallback_reason,
            )

        if downloaded < total:
            raise DownloadError(f"only {downloaded} of {total} bytes were downloaded")
        size = target.stat().st_size
        if size != total:
            raise DownloadError(f"target file has {size} bytes, expected {total}")

        self._sync_state(state, pool)
        state.completed = True
        _save_state(context, state)
        context.store.remove()
        snapshot = self._multi_snapshot(
            context,
            total,
            total,
            node_pool,
            meter,
            worker_count,
            fallback_used=fallback_used,
            fallback_bytes=fallback_bytes,
            done=True,
        )
        self._notify(context, snapshot, force=True)
        return DownloadResult(
            target=target,
            total=total,
            downloaded=total,
            ok=True,
            resumed_bytes=resumed_bytes,
            fallback_reason=fallback_reason,
        )

    def _worker(
        self,
        worker_id: int,
        context: _Run,
        pool: SegmentPool,
        node_pool: NodePool,
        throttle: ThrottlePolicy,
        coordinator: _Coordinator,
        head: HeadInfo,
        total: int,
        multi_node: bool,
    ) -> None:
        options = context.options
        try:
            handle = open(options.target, "r+b")  # noqa: SIM115 - closed below
        except OSError as exc:
            coordinator.fail(DownloadError(f"could not open the target file: {exc}"))
            return
        with handle:
            while not context.stop.is_set() and not coordinator.should_abort():
                route = node_pool.next_available(worker_id)
                if route is None:
                    coordinator.trigger_degrade("all proxy nodes failed")
                    return
                segment = pool.next_task(worker_id, route.name)
                if segment is None:
                    return
                try:
                    self._stream_segment(
                        context,
                        handle,
                        segment,
                        route,
                        head,
                        node_pool,
                        throttle,
                        coordinator.should_abort,
                        pool,
                    )
                except _Cancelled:
                    pool.requeue(segment)
                    return
                except HttpStatusError as exc:
                    pool.requeue(segment)
                    segment.attempts += 1
                    if segment.attempts > max(1, options.max_retries):
                        coordinator.fail(
                            DownloadError(
                                f"HTTP {exc.status} kept failing for bytes "
                                f"{segment.start}-{segment.end}"
                            )
                        )
                        return
                    if exc.status in _THROTTLE_STATUSES:
                        throttle.record(route.name, exc.status)
                        if throttle.should_degrade():
                            for name in throttle.throttled_nodes:
                                node_pool.mark_failed(name, f"HTTP {exc.status}")
                            coordinator.trigger_degrade(
                                throttle.reason() or "too many HTTP 403/429 responses"
                            )
                            return
                        context.sleep(_backoff_delay(segment.attempts))
                        continue
                    if exc.status >= 500:
                        node_pool.mark_failed(route.name, f"HTTP {exc.status}")
                        if multi_node and not node_pool.healthy_nodes:
                            coordinator.trigger_degrade(
                                f"all nodes failed with HTTP {exc.status}"
                            )
                            return
                        context.sleep(_backoff_delay(segment.attempts))
                        continue
                    coordinator.fail(
                        DownloadError(f"HTTP {exc.status} for {options.target.name}")
                    )
                    return
                except NodeFailed as exc:
                    pool.requeue(segment)
                    segment.attempts += 1
                    if segment.attempts > max(1, options.max_retries):
                        coordinator.fail(
                            DownloadError(f"node {route.name} failed too often: {exc}")
                        )
                        return
                    if multi_node:
                        node_pool.mark_failed(route.name, str(exc) or "node failed")
                        if not node_pool.healthy_nodes:
                            coordinator.trigger_degrade(f"all nodes failed: {exc}")
                            return
                        context.sleep(_backoff_delay(1))
                    else:
                        context.sleep(_backoff_delay(segment.attempts))
                    continue
                except RangeNotSupported as exc:
                    pool.requeue(segment)
                    coordinator.fail(
                        DownloadError(f"server stopped supporting byte ranges: {exc}")
                    )
                    return
                pool.mark_done(segment, segment.done)
        if _pool_downloaded(pool) > total:
            log.debug("worker %d saw more bytes than expected", worker_id)

    def _drain_fallback(
        self,
        context: _Run,
        state: DownloadState,
        pool: SegmentPool,
        node_pool: NodePool,
        meter: _Meter,
        head: HeadInfo,
        total: int,
        worker_count: int,
    ) -> None:
        options = context.options
        route = NodeRoute(_FALLBACK_NODE, options.proxy_port)
        worker_id = 10_000
        handle = prepare_target(options.target, total)
        try:
            while not context.stop.is_set():
                segment = pool.next_task(worker_id, route.name)
                if segment is None:
                    return
                attempts = segment.attempts
                while segment.remaining > 0 and not context.stop.is_set():
                    before = segment.done
                    try:
                        self._stream_segment(
                            context,
                            handle,
                            segment,
                            route,
                            head,
                            None,
                            None,
                            None,
                            pool,
                        )
                    except _Cancelled:
                        pool.requeue(segment)
                        return
                    except (NodeFailed, HttpStatusError, RangeNotSupported) as exc:
                        if isinstance(exc, RangeNotSupported) or not _retryable(exc):
                            raise DownloadError(f"fallback download failed: {exc}") from exc
                        attempts += 1
                        segment.attempts = attempts
                        if attempts > max(1, options.max_retries):
                            raise DownloadError(
                                f"fallback proxy failed after {options.max_retries} retries: {exc}"
                            ) from exc
                        context.sleep(_backoff_delay(attempts))
                        continue
                    if segment.done <= before and segment.remaining > 0:
                        attempts += 1
                        segment.attempts = attempts
                        if attempts > max(1, options.max_retries):
                            raise DownloadError("fallback proxy returned no data")
                        context.sleep(_backoff_delay(attempts))
                pool.mark_done(segment, segment.done)
                self._sync_state(state, pool)
                self._notify(
                    context,
                    self._multi_snapshot(
                        context,
                        total,
                        _pool_downloaded(pool),
                        node_pool,
                        meter,
                        worker_count,
                        fallback_used=True,
                    ),
                    state,
                )
        finally:
            handle.close()

    def _stream_segment(
        self,
        context: _Run,
        handle: BinaryIO,
        segment: Segment,
        route: NodeRoute,
        head: HeadInfo,
        node_pool: NodePool | None,
        throttle: ThrottlePolicy | None,
        abort_check: Callable[[], bool] | None,
        pool: SegmentPool | None,
    ) -> None:
        url = head.final_url or head.url
        pos = segment.position
        while True:
            if context.stop.is_set():
                raise _Cancelled
            if abort_check is not None and abort_check():
                raise _Cancelled
            limit = segment.end
            if pos >= limit:
                return
            request_end = min(limit, pos + context.window) - 1
            stream = context.transport.get_range(
                url,
                route.port,
                pos,
                request_end,
                etag=head.etag,
                last_modified=head.last_modified,
            )
            try:
                for chunk in stream:
                    if context.stop.is_set():
                        raise _Cancelled
                    if abort_check is not None and abort_check():
                        raise _Cancelled
                    limit = segment.end
                    if pos >= limit:
                        return
                    if not chunk:
                        continue
                    data = chunk[: limit - pos]
                    handle.seek(pos)
                    handle.write(data)
                    pos += len(data)
                    if pool is not None:
                        pool.add_progress(segment, len(data))
                    else:
                        segment.done = min(segment.length, segment.done + len(data))
                    if node_pool is not None:
                        node_pool.record_bytes(route.name, len(data))
                    if throttle is not None:
                        throttle.record_success(route.name)
            finally:
                _close_stream(stream)

    # -- snapshot helpers --------------------------------------------------
    def _single_snapshot(
        self,
        context: _Run,
        total: int,
        downloaded: int,
        meter: _Meter,
        *,
        done: bool = False,
        error: str = "",
    ) -> DownloadSnapshot:
        speed = meter.update(downloaded)
        remaining = max(0, total - downloaded)
        eta = remaining / speed if speed > 1e-6 else 0.0
        node = NodeState(
            name=_SINGLE_NODE,
            state="ok",
            downloaded=downloaded,
            speed=speed,
        )
        return DownloadSnapshot(
            total=total,
            downloaded=downloaded,
            speed=speed,
            eta_seconds=eta,
            threads=1,
            done=done,
            error=error,
            nodes=(node,),
        )

    def _multi_snapshot(
        self,
        context: _Run,
        total: int,
        downloaded: int,
        node_pool: NodePool,
        meter: _Meter,
        threads: int,
        *,
        fallback_used: bool = False,
        fallback_bytes: int = 0,
        done: bool = False,
        error: str = "",
    ) -> DownloadSnapshot:
        speed = meter.update(downloaded)
        remaining = max(0, total - downloaded)
        eta = remaining / speed if speed > 1e-6 else 0.0
        node_pool.refresh_speeds()
        nodes = list(node_pool.states())
        if fallback_used and all(node.name != _FALLBACK_NODE for node in nodes):
            nodes.append(
                NodeState(
                    name=_FALLBACK_NODE,
                    state="ok",
                    downloaded=fallback_bytes,
                    speed=speed,
                )
            )
        return DownloadSnapshot(
            total=total,
            downloaded=downloaded,
            speed=speed,
            eta_seconds=eta,
            threads=threads,
            done=done,
            error=error,
            nodes=tuple(nodes),
        )

    def _notify(
        self,
        context: _Run,
        snapshot: DownloadSnapshot,
        state: DownloadState | None = None,
        *,
        force: bool = False,
    ) -> None:
        now = context.clock()
        interval = max(0.01, context.options.progress_interval)
        if not force and (now - context.last_emit) < interval:
            return
        context.last_emit = now
        try:
            context.emit(snapshot)
        except Exception:
            log.exception("download progress callback failed")
        if state is not None:
            _save_state(context, state)

    @staticmethod
    def _sync_state(state: DownloadState, pool: SegmentPool) -> None:
        state.segments = [
            SegmentState(
                start=segment.start,
                end=segment.end,
                done=segment.done,
                attempts=segment.attempts,
                node=segment.node,
            )
            for segment in pool.snapshot()
        ]


def _ignore_snapshot(snapshot: DownloadSnapshot) -> None:
    del snapshot


def _unknown_head(url: str) -> HeadInfo:
    """Synthetic probe result used when HEAD is unusable (405/403/no ranges)."""
    return HeadInfo(
        url=url,
        final_url=url,
        status=0,
        content_length=-1,
        accept_ranges=False,
    )


def _backoff_delay(attempt: int) -> float:
    exponent = max(0, int(attempt) - 1)
    return min(_BASE_BACKOFF * (2**exponent), _MAX_BACKOFF)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, NodeFailed):
        return True
    if isinstance(exc, HttpStatusError):
        return exc.status in _THROTTLE_STATUSES or exc.status >= 500
    return False


def _pool_downloaded(pool: SegmentPool) -> int:
    return sum(segment.done for segment in pool.snapshot())


def _single_segment_done(state: DownloadState | None, total: int) -> int | None:
    if state is None or len(state.segments) != 1:
        return None
    segment = state.segments[0]
    if segment.start != 0 or segment.end != total:
        return None
    return max(0, min(segment.done, total))


def _segment_from_state(item: SegmentState, total: int) -> Segment:
    start = max(0, min(item.start, total))
    end = max(start, min(item.end, total))
    done = max(0, min(item.done, end - start))
    return Segment(
        start=start,
        end=end,
        done=done,
        attempts=max(0, item.attempts),
        node=item.node,
    )


def _segments_cover(segments: Sequence[Segment], total: int) -> bool:
    if total <= 0:
        return False
    ordered = sorted(segments, key=lambda segment: segment.start)
    cursor = 0
    for segment in ordered:
        if segment.start != cursor:
            return False
        cursor = segment.end
    return cursor == total


def _save_state(context: _Run, state: DownloadState) -> None:
    try:
        context.store.save(state)
    except OSError as exc:
        log.warning("could not save download state: %s", exc)


def _close_stream(stream: object) -> None:
    close = getattr(stream, "close", None)
    if close is not None:
        with contextlib.suppress(Exception):
            close()
