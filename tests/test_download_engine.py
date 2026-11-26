"""Tests for the pure-Python download engine.

Everything is served from an in-memory FakeTransport; no sockets are opened.
"""

from __future__ import annotations

import threading

import pytest

from mihomo_lite.download import engine as engine_module
from mihomo_lite.download.engine import DownloadEngine
from mihomo_lite.download.planner import auto_thread_count, plan
from mihomo_lite.download.resume import (
    DownloadState,
    SegmentState,
    StateStore,
    default_state_path,
    state_matches,
)
from mihomo_lite.download.scheduler import NodePool, SegmentPool, ThrottlePolicy
from mihomo_lite.download.types import (
    DownloadOptions,
    HeadInfo,
    HttpStatusError,
    NodeFailed,
    NodeRoute,
    RangeNotSupported,
)

MIB = 1024 * 1024


def payload(size: int) -> bytes:
    base = bytes(range(256))
    repeats, remainder = divmod(size, len(base))
    return base * repeats + base[:remainder]


class FakeTransport:
    """In-memory transport double; optionally fails or throttles per port."""

    def __init__(
        self,
        data: bytes = b"",
        *,
        accept_ranges: bool = True,
        content_length: int | None = None,
        etag: str = "",
        last_modified: str = "",
        chunk: int = 16384,
        head_status: int = 200,
        range_supported: bool = True,
    ) -> None:
        self.data = data
        self.accept_ranges = accept_ranges
        self.content_length = len(data) if content_length is None else content_length
        self.etag = etag
        self.last_modified = last_modified
        self.chunk = max(1, chunk)
        self.head_status = head_status
        self.range_supported = range_supported
        self.range_requests: list[tuple[int, int, int]] = []
        self.full_requests: list[int] = []
        self.head_calls: list[int] = []
        self.bytes_served = 0
        self.fail_next: list[BaseException] = []
        self.fail_ports: set[int] = set()
        self.status_ports: dict[int, int] = {}
        self.on_chunk = None
        self.barrier: threading.Barrier | None = None
        self._lock = threading.Lock()

    def head(self, url: str, proxy_port: int) -> HeadInfo:
        self.head_calls.append(proxy_port)
        if self.head_status >= 500:
            raise NodeFailed(f"HEAD returned HTTP {self.head_status}")
        if self.head_status == 405:
            raise RangeNotSupported("server rejected HEAD with HTTP 405")
        if self.head_status >= 400:
            raise HttpStatusError(self.head_status)
        return HeadInfo(
            url=url,
            final_url=url,
            status=self.head_status,
            content_length=self.content_length,
            accept_ranges=self.accept_ranges,
            etag=self.etag,
            last_modified=self.last_modified,
        )

    def get_range(self, url, proxy_port, start, end, *, etag="", last_modified=""):
        with self._lock:
            self.range_requests.append((proxy_port, start, end))
            if self.fail_next:
                raise self.fail_next.pop(0)
        if proxy_port in self.status_ports:
            raise HttpStatusError(self.status_ports[proxy_port])
        if proxy_port in self.fail_ports:
            raise NodeFailed(f"connection refused via port {proxy_port}")
        if not self.range_supported:
            raise RangeNotSupported("server does not support byte ranges")
        if self.barrier is not None:
            self.barrier.wait()
        stop = min(end, len(self.data) - 1)
        if start > stop:
            return
        cursor = start
        while cursor <= stop:
            limit = min(stop + 1, cursor + self.chunk)
            block = self.data[cursor:limit]
            self.bytes_served += len(block)
            if self.on_chunk is not None:
                self.on_chunk(len(block))
            yield block
            cursor = limit

    def get_full(self, url, proxy_port):
        with self._lock:
            self.full_requests.append(proxy_port)
            if self.fail_next:
                raise self.fail_next.pop(0)
        if proxy_port in self.status_ports:
            raise HttpStatusError(self.status_ports[proxy_port])
        if proxy_port in self.fail_ports:
            raise NodeFailed(f"connection refused via port {proxy_port}")
        cursor = 0
        while cursor < len(self.data):
            limit = min(len(self.data), cursor + self.chunk)
            block = self.data[cursor:limit]
            self.bytes_served += len(block)
            if self.on_chunk is not None:
                self.on_chunk(len(block))
            yield block
            cursor = limit


def make_engine(transport, *, sleeps=None):
    if sleeps is None:
        return DownloadEngine(transport_factory=lambda: transport, sleep=lambda _delay: None)
    return DownloadEngine(transport_factory=lambda: transport, sleep=sleeps.append)


def options_for(tmp_path, data, **overrides) -> DownloadOptions:
    values = {
        "url": "http://download.test/payload.bin",
        "target": tmp_path / "payload.bin",
        "proxy_port": 7890,
    }
    values.update(overrides)
    return DownloadOptions(**values)


# -- basic paths ---------------------------------------------------------------


def test_single_thread_writes_file(tmp_path):
    data = payload(300_000)
    transport = FakeTransport(data)
    engine = make_engine(transport)
    target = tmp_path / "payload.bin"

    result = engine.run(options_for(tmp_path, data))

    assert result.ok, result.error
    assert result.target == target
    assert result.total == len(data)
    assert result.downloaded == len(data)
    assert target.read_bytes() == data
    assert not default_state_path(target).exists()


def test_head_no_accept_ranges_falls_back_single_thread(tmp_path):
    data = payload(200_000)
    transport = FakeTransport(data, accept_ranges=False, range_supported=False)
    engine = make_engine(transport)
    snapshots = []
    target = tmp_path / "payload.bin"

    result = engine.run(
        options_for(tmp_path, data, thread_count=4, multithreaded=True),
        on_snapshot=snapshots.append,
    )

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert result.fallback_reason
    assert "range" in result.fallback_reason.lower()
    assert result.resumed_bytes == 0
    assert transport.range_requests == []
    assert transport.full_requests
    assert snapshots
    assert snapshots[-1].done is True
    assert snapshots[-1].threads == 1


def test_head_405_uses_plain_get_with_unknown_length(tmp_path):
    data = payload(150_000)
    transport = FakeTransport(
        data,
        accept_ranges=False,
        head_status=405,
        range_supported=False,
    )
    engine = make_engine(transport)
    snapshots = []
    target = tmp_path / "payload.bin"

    result = engine.run(
        options_for(tmp_path, data, thread_count=4, multithreaded=True),
        on_snapshot=snapshots.append,
    )

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert result.total == len(data)
    assert result.downloaded == len(data)
    assert result.fallback_reason
    assert result.resumed_bytes == 0
    assert transport.range_requests == []
    assert transport.full_requests
    assert snapshots[-1].done is True
    assert snapshots[-1].threads == 1


def test_no_state_file_after_success(tmp_path):
    data = payload(600_000)
    transport = FakeTransport(data)
    engine = make_engine(transport)
    target = tmp_path / "payload.bin"

    result = engine.run(
        options_for(tmp_path, data, thread_count=4, multithreaded=True)
    )

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert not default_state_path(target).exists()


# -- planning ------------------------------------------------------------------


def test_auto_thread_count():
    assert auto_thread_count(0) == 4
    assert auto_thread_count(1024) == 4
    assert auto_thread_count(16 * MIB - 1) == 4
    assert auto_thread_count(16 * MIB) == 8
    assert auto_thread_count(64 * MIB - 1) == 8
    assert auto_thread_count(64 * MIB) == 12
    assert auto_thread_count(256 * MIB - 1) == 12
    assert auto_thread_count(256 * MIB) == 16
    assert auto_thread_count(5 * MIB, requested=7) == 7
    assert auto_thread_count(5 * MIB, requested=2) == 4
    assert auto_thread_count(300 * MIB, requested=99) == 16
    assert auto_thread_count(0, requested=0) == 4


def test_plan_single_thread_conditions(tmp_path):
    base = DownloadOptions(url="http://x.test/a", target=tmp_path / "a", proxy_port=7890)
    ranged = HeadInfo(
        url="http://x.test/a",
        final_url="http://x.test/a",
        status=200,
        content_length=32 * MIB,
        accept_ranges=True,
    )

    no_ranges = HeadInfo(
        url=ranged.url,
        final_url=ranged.final_url,
        status=200,
        content_length=ranged.content_length,
        accept_ranges=False,
    )
    unknown_size = HeadInfo(
        url=ranged.url,
        final_url=ranged.final_url,
        status=200,
        content_length=-1,
        accept_ranges=True,
    )

    assert plan(no_ranges, base).supports_ranges is False
    assert plan(no_ranges, base).thread_count == 1
    assert plan(unknown_size, base).thread_count == 1
    assert plan(ranged, base).thread_count == 1
    assert plan(ranged, DownloadOptions(
        url=base.url,
        target=base.target,
        proxy_port=base.proxy_port,
        multithreaded=True,
        thread_count=0,
    )).thread_count == 8


# -- parallel coverage ---------------------------------------------------------


def test_multithread_segments_cover_file_without_overlap(tmp_path):
    data = payload(8 * MIB)
    transport = FakeTransport(data, chunk=65536)
    transport.barrier = threading.Barrier(8, timeout=10)
    engine = make_engine(transport)
    target = tmp_path / "payload.bin"

    result = engine.run(
        options_for(tmp_path, data, thread_count=8, multithreaded=True)
    )

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert result.resumed_bytes == 0

    requests = sorted((start, end) for _port, start, end in transport.range_requests)
    assert len(requests) == 8
    assert requests[0][0] == 0
    for previous, current in zip(requests, requests[1:], strict=False):
        assert current[0] == previous[1] + 1
    assert requests[-1][1] == len(data) - 1


def test_dynamic_split_longest_segment():
    pool = SegmentPool(8 * MIB, 2)
    first = pool.next_task(0, "node-a")
    second = pool.next_task(1, "node-b")
    assert first is not None and first.start == 0 and first.end == 4 * MIB
    assert second is not None and second.start == 4 * MIB and second.end == 8 * MIB

    split = pool.next_task(2, "node-a")
    assert split is not None
    assert split.start == 2 * MIB
    assert split.end == 4 * MIB
    assert first.end == 2 * MIB

    ordered = sorted(pool.snapshot(), key=lambda segment: segment.start)
    cursor = 0
    for segment in ordered:
        assert segment.start == cursor
        cursor = segment.end
    assert cursor == 8 * MIB

    pool.mark_done(first, first.length)
    pool.mark_done(second, second.length)
    pool.mark_done(split, split.length)
    assert pool.is_complete()
    assert pool.remaining() == 0


def test_dynamic_split_respects_min_split():
    pool = SegmentPool(2 * MIB, 1)
    assert pool.next_task(0, "node-a") is not None
    splinter = pool.next_task(1, "node-b")
    assert splinter is not None
    assert splinter.start == MIB
    assert pool.next_task(2, "node-c") is None


def test_single_node_route_still_uses_thread_count_workers(tmp_path):
    data = payload(2 * MIB)
    transport = FakeTransport(data, chunk=65536)
    engine = make_engine(transport)
    routes = (NodeRoute("only-node", 1101),)
    target = tmp_path / "payload.bin"
    snapshots = []

    result = engine.run(
        options_for(
            tmp_path,
            data,
            proxy_port=1100,
            thread_count=4,
            multithreaded=True,
            multi_node=True,
            node_routes=routes,
        ),
        on_snapshot=snapshots.append,
    )

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert result.fallback_reason == ""
    assert snapshots[-1].threads == 4
    assert transport.range_requests
    assert all(port == 1101 for port, _start, _end in transport.range_requests)


# -- retries and cancellation --------------------------------------------------


def test_retry_exponential_backoff_capped_at_5(tmp_path):
    data = payload(128_000)
    transport = FakeTransport(data)
    transport.fail_next = [NodeFailed("temporary failure") for _ in range(5)]
    sleeps: list[float] = []
    engine = make_engine(transport, sleeps=sleeps)
    target = tmp_path / "payload.bin"

    result = engine.run(options_for(tmp_path, data))

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert len(sleeps) == 5
    expected = [
        min(engine_module._BASE_BACKOFF * (2**index), engine_module._MAX_BACKOFF)
        for index in range(5)
    ]
    assert sleeps == pytest.approx(expected)
    assert all(delay <= engine_module._MAX_BACKOFF for delay in sleeps)


def test_cancel_stops_and_saves_state(tmp_path):
    data = payload(1_000_000)
    transport = FakeTransport(data, chunk=16384)
    cancel = threading.Event()

    def on_chunk(_count):
        if transport.bytes_served >= 200_000:
            cancel.set()

    transport.on_chunk = on_chunk
    engine = make_engine(transport)
    target = tmp_path / "payload.bin"
    state_path = tmp_path / "payload.state.json"

    result = engine.run(
        options_for(tmp_path, data, state_path=state_path),
        cancel=cancel,
    )

    assert result.ok is False
    assert result.error == "cancelled"
    assert result.downloaded < len(data)
    assert target.exists()
    assert target.stat().st_size == len(data)
    assert state_path.exists()
    saved = StateStore(state_path).load()
    assert saved is not None
    assert len(saved.segments) == 1
    assert 0 < saved.segments[0].done < len(data)


def test_resume_after_partial_state(tmp_path):
    data = payload(1_200_000)
    target = tmp_path / "payload.bin"
    state_path = tmp_path / "payload.state.json"
    cancel = threading.Event()

    first_transport = FakeTransport(data, chunk=16384)

    def on_chunk(_count):
        if first_transport.bytes_served >= 200_000:
            cancel.set()

    first_transport.on_chunk = on_chunk
    first_engine = make_engine(first_transport)
    first = first_engine.run(
        options_for(tmp_path, data, state_path=state_path),
        cancel=cancel,
    )
    assert first.ok is False and first.error == "cancelled"
    saved = StateStore(state_path).load()
    assert saved is not None
    resumed_at = saved.segments[0].done
    assert 0 < resumed_at < len(data)

    second_transport = FakeTransport(data)
    second_engine = make_engine(second_transport)
    second = second_engine.run(
        options_for(tmp_path, data, state_path=state_path)
    )

    assert second.ok, second.error
    assert second.resumed_bytes == resumed_at
    assert target.read_bytes() == data
    assert second_transport.range_requests[0][1] == resumed_at
    assert not state_path.exists()


def test_etag_change_restarts(tmp_path):
    data = payload(800_000)
    target = tmp_path / "payload.bin"
    state_path = tmp_path / "payload.state.json"
    cancel = threading.Event()

    first_transport = FakeTransport(data, chunk=16384, etag="v1")
    first_transport.on_chunk = lambda _count: cancel.set() if first_transport.bytes_served >= 100_000 else None
    first_engine = make_engine(first_transport)
    first = first_engine.run(
        options_for(tmp_path, data, state_path=state_path),
        cancel=cancel,
    )
    assert first.ok is False
    saved = StateStore(state_path).load()
    assert saved is not None
    assert saved.etag == "v1"
    assert saved.segments[0].done > 0

    second_transport = FakeTransport(data, etag="v2")
    second_engine = make_engine(second_transport)
    second = second_engine.run(
        options_for(tmp_path, data, state_path=state_path)
    )

    assert second.ok, second.error
    assert second.resumed_bytes == 0
    assert target.read_bytes() == data
    assert second_transport.range_requests[0][1] == 0
    assert not state_path.exists()


# -- nodes, throttling ---------------------------------------------------------


def test_node_failure_reassigns_segments(tmp_path):
    data = payload(4 * MIB)
    transport = FakeTransport(data, chunk=65536)
    transport.fail_ports.add(1102)
    engine = make_engine(transport)
    routes = (NodeRoute("node-a", 1101), NodeRoute("node-b", 1102))
    target = tmp_path / "payload.bin"
    snapshots = []

    result = engine.run(
        options_for(
            tmp_path,
            data,
            proxy_port=1100,
            thread_count=4,
            multithreaded=True,
            multi_node=True,
            node_routes=routes,
        ),
        on_snapshot=snapshots.append,
    )

    assert result.ok, result.error
    assert target.read_bytes() == data
    assert result.fallback_reason == ""
    assert snapshots and snapshots[-1].done is True
    nodes = {node.name: node for node in snapshots[-1].nodes}
    assert nodes["node-b"].state == "error"
    assert nodes["node-b"].message
    assert nodes["node-a"].state == "ok"


def test_403_429_degrades_to_single_node(tmp_path):
    data = payload(2 * MIB)
    transport = FakeTransport(data)
    transport.status_ports = {1101: 403, 1102: 429}
    engine = make_engine(transport)
    routes = (NodeRoute("node-a", 1101), NodeRoute("node-b", 1102))
    target = tmp_path / "payload.bin"
    snapshots = []

    result = engine.run(
        options_for(
            tmp_path,
            data,
            proxy_port=1100,
            thread_count=4,
            multithreaded=True,
            multi_node=True,
            node_routes=routes,
        ),
        on_snapshot=snapshots.append,
    )

    assert result.ok, result.error
    assert result.fallback_reason
    assert "403/429" in result.fallback_reason or "403" in result.fallback_reason
    assert target.read_bytes() == data
    assert snapshots and snapshots[-1].done is True
    fallback_nodes = [node for node in snapshots[-1].nodes if node.name == "single"]
    assert fallback_nodes


def test_node_pool_reports_and_isolates_failed_nodes():
    pool = NodePool((NodeRoute("a", 1), NodeRoute("b", 2)))
    assert pool.next_available(0).name == "a"
    assert pool.next_available(1).name == "b"
    pool.mark_failed("a", "boom")
    assert [route.name for route in pool.healthy_nodes] == ["b"]
    assert pool.next_available(0).name == "b"
    assert pool.next_available(2).name == "b"
    states = {node.name: node for node in pool.states()}
    assert states["a"].state == "error"
    assert states["a"].message == "boom"
    assert states["b"].state == "ok"
    pool.mark_failed("b")
    assert pool.next_available(0) is None


def test_throttle_policy_degrades_after_two_nodes_or_three_strikes():
    policy = ThrottlePolicy()
    assert policy.record("a", 403) is True
    assert policy.should_degrade() is False
    assert policy.record("b", 429) is True
    assert policy.should_degrade() is True
    assert "403/429" in policy.reason()

    streak = ThrottlePolicy()
    for _ in range(3):
        streak.record("a", 403)
    assert streak.should_degrade() is True
    assert "in a row" in streak.reason()
    streak.record_success("a")
    assert streak.should_degrade() is False
    streak.record("b", 403)
    assert streak.should_degrade() is True


# -- resume primitives ---------------------------------------------------------


def test_state_store_round_trip_and_mismatch(tmp_path):
    head = HeadInfo(
        url="http://x.test/a",
        final_url="http://x.test/a",
        status=200,
        content_length=1000,
        accept_ranges=True,
        etag="abc",
        last_modified="Mon",
    )
    state = DownloadState(
        url=head.final_url,
        total=head.content_length,
        etag=head.etag,
        last_modified=head.last_modified,
        accept_ranges=True,
        segments=[SegmentState(0, 1000, done=400, attempts=1, node="a")],
    )
    store = StateStore(tmp_path / "state.json")
    store.save(state)
    loaded = store.load()
    assert loaded is not None
    assert loaded.segments == [SegmentState(0, 1000, done=400, attempts=1, node="a")]
    assert state_matches(loaded, head) is True

    changed = HeadInfo(
        url=head.url,
        final_url=head.final_url,
        status=200,
        content_length=head.content_length,
        accept_ranges=True,
        etag="different",
        last_modified=head.last_modified,
    )
    assert state_matches(loaded, changed) is False
    store.remove()
    assert store.load() is None
