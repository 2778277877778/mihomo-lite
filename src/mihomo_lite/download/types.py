"""Value objects and exceptions shared by the download engine.

The package is pure Python (standard library plus httpx) and must never import
PySide6: the engine runs on worker threads owned by the GUI layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class DownloadError(Exception):
    """Raised when a download cannot be completed."""


class HttpStatusError(DownloadError):
    """The transport received a non-success HTTP status."""

    def __init__(self, status: int, message: str = "") -> None:
        self.status = int(status)
        super().__init__(message or f"HTTP {self.status}")


class RangeNotSupported(DownloadError):
    """The server answered a Range request without partial content."""


class NodeFailed(DownloadError):
    """A node/route failed at the transport level (connect, timeout, 5xx)."""

    def __init__(self, message: str = "node failed", node: str = "") -> None:
        self.node = node
        super().__init__(message)


@dataclass(frozen=True)
class NodeRoute:
    """One local proxy port that can serve range requests."""

    name: str
    port: int


@dataclass(frozen=True)
class DownloadOptions:
    """Everything the engine needs to perform one download."""

    url: str
    target: Path
    proxy_port: int
    thread_count: int = 8
    multithreaded: bool = False
    multi_node: bool = False
    node_routes: tuple[NodeRoute, ...] = ()
    max_retries: int = 5
    chunk_size: int = 65536
    state_path: Path | None = None
    progress_interval: float = 0.4


@dataclass(frozen=True)
class HeadInfo:
    """Result of a HEAD probe.

    A negative content_length means the server did not report one; zero means
    the resource is empty.
    """

    url: str
    final_url: str
    status: int
    content_length: int
    accept_ranges: bool
    etag: str = ""
    last_modified: str = ""


@dataclass(frozen=True)
class NodeState:
    """Snapshot of one node used by a running download."""

    name: str
    state: str
    downloaded: int = 0
    speed: float = 0.0
    message: str = ""


@dataclass(frozen=True)
class DownloadSnapshot:
    """Progress callback payload."""

    total: int
    downloaded: int
    speed: float
    eta_seconds: float
    threads: int
    done: bool
    error: str = ""
    nodes: tuple[NodeState, ...] = ()


@dataclass
class DownloadResult:
    """Final result returned by DownloadEngine.run()."""

    target: Path
    total: int
    downloaded: int
    ok: bool
    error: str = ""
    resumed_bytes: int = 0
    fallback_reason: str = ""
