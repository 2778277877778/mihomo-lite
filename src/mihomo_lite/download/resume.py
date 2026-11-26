"""On-disk download state used for resuming interrupted downloads."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

from mihomo_lite.download.types import HeadInfo

log = logging.getLogger(__name__)

STATE_SUFFIX = ".mihomo-download.json"


def default_state_path(target: Path) -> Path:
    """Default sidecar state file next to the target file."""
    return target.with_name(target.name + STATE_SUFFIX)


@dataclass
class SegmentState:
    """Persisted progress for one byte range [start, end)."""

    start: int
    end: int
    done: int = 0
    attempts: int = 0
    node: str = ""

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def remaining(self) -> int:
        return max(0, self.length - self.done)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "done": self.done,
            "attempts": self.attempts,
            "node": self.node,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SegmentState:
        if not isinstance(data, dict):
            raise ValueError("segment entry is not an object")
        start = int(data["start"])
        end = int(data["end"])
        done = int(data.get("done", 0))
        attempts = int(data.get("attempts", 0))
        node = str(data.get("node", ""))
        if start < 0 or end < start:
            raise ValueError("segment bounds are invalid")
        return cls(
            start=start,
            end=end,
            done=max(0, min(done, end - start)),
            attempts=max(0, attempts),
            node=node,
        )


@dataclass
class DownloadState:
    """Serialized progress of a single download."""

    url: str
    total: int
    etag: str = ""
    last_modified: str = ""
    accept_ranges: bool = False
    segments: list[SegmentState] = field(default_factory=list)
    updated_at: float = 0.0
    completed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "url": self.url,
            "total": self.total,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "accept_ranges": self.accept_ranges,
            "segments": [segment.to_dict() for segment in self.segments],
            "updated_at": self.updated_at,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: Any) -> DownloadState:
        if not isinstance(data, dict):
            raise ValueError("download state is not an object")
        raw_segments = data.get("segments", [])
        if not isinstance(raw_segments, list):
            raise ValueError("segments is not a list")
        return cls(
            url=str(data["url"]),
            total=int(data["total"]),
            etag=str(data.get("etag", "")),
            last_modified=str(data.get("last_modified", "")),
            accept_ranges=bool(data.get("accept_ranges", False)),
            segments=[SegmentState.from_dict(item) for item in raw_segments],
            updated_at=float(data.get("updated_at", 0.0)),
            completed=bool(data.get("completed", False)),
        )


def new_state(head: HeadInfo) -> DownloadState:
    """Create a fresh state object for a probe result."""
    return DownloadState(
        url=head.final_url or head.url,
        total=max(0, head.content_length),
        etag=head.etag,
        last_modified=head.last_modified,
        accept_ranges=bool(head.accept_ranges),
        segments=[],
        updated_at=time.time(),
        completed=False,
    )


def state_matches(state: DownloadState | None, head: HeadInfo) -> bool:
    """True when a saved state can be resumed for the probed resource."""
    if state is None or state.completed:
        return False
    if state.url != (head.final_url or head.url):
        return False
    if state.total != max(0, head.content_length):
        return False
    if state.etag != head.etag:
        return False
    if state.last_modified != head.last_modified:
        return False
    return bool(state.accept_ranges) == bool(head.accept_ranges)


def prepare_target(target: Path, total: int) -> BinaryIO:
    """Open/create the target file and preallocate it to total bytes."""
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = "r+b" if target.exists() else "w+b"
    handle = open(target, mode)  # noqa: SIM115 - caller owns the handle
    try:
        handle.truncate(max(0, total))
    except BaseException:
        handle.close()
        raise
    return handle


class StateStore:
    """Atomic JSON storage for DownloadState."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> DownloadState | None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            log.warning("could not read download state: %s", exc)
            return None
        try:
            return DownloadState.from_dict(json.loads(raw))
        except (ValueError, TypeError, KeyError) as exc:
            log.warning("ignoring invalid download state: %s", exc)
            return None

    def save(self, state: DownloadState) -> None:
        state.updated_at = time.time()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=self._path.name + ".",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(state.to_dict(), handle, ensure_ascii=False)
            os.replace(temporary, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise

    def remove(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()
