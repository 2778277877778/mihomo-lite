"""Transport abstractions used by the download engine.

Only loopback proxies are contacted; httpx is configured with trust_env=False
so environment proxy variables never bypass the mihomo mixed-port.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Protocol

import httpx

from mihomo_lite.download.types import HeadInfo, HttpStatusError, NodeFailed, RangeNotSupported

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0

_THROTTLE_STATUSES = (403, 429)


class Transport(Protocol):
    """Minimal HTTP surface the engine needs."""

    def head(self, url: str, proxy_port: int) -> HeadInfo:
        """Probe the resource without downloading a body."""
        ...

    def get_full(self, url: str, proxy_port: int) -> Iterator[bytes]:
        """Yield the complete body with a plain GET (no Range header)."""
        ...

    def get_range(
        self,
        url: str,
        proxy_port: int,
        start: int,
        end: int,
        *,
        etag: str = "",
        last_modified: str = "",
    ) -> Iterator[bytes]:
        """Yield the body bytes for the inclusive byte range start..end."""
        ...


def _client(proxy_port: int, timeout: float) -> httpx.Client:
    return httpx.Client(
        proxy=f"http://127.0.0.1:{proxy_port}",
        trust_env=False,
        follow_redirects=True,
        timeout=timeout,
    )


def _header_contains_bytes(value: str) -> bool:
    return "bytes" in value.lower()


def _parse_content_range(value: str, start: int, end: int) -> None:
    """Validate a Content-Range header for the requested inclusive range."""
    if not value:
        raise RangeNotSupported("missing Content-Range header")
    text = value.strip()
    if not text.lower().startswith("bytes "):
        raise RangeNotSupported(f"unsupported Content-Range: {value}")
    span, _, total_text = text[6:].strip().partition("/")
    first, _, last = span.partition("-")
    try:
        actual_start = int(first)
        actual_end = int(last)
        total = int(total_text.strip()) if total_text.strip() != "*" else -1
    except ValueError as exc:
        raise RangeNotSupported(f"malformed Content-Range: {value}") from exc
    if actual_start != start:
        raise RangeNotSupported(f"unexpected Content-Range start: {value}")
    if actual_end < actual_start or actual_end > end:
        raise RangeNotSupported(f"unexpected Content-Range span: {value}")
    if total >= 0 and actual_end >= total:
        raise RangeNotSupported(f"Content-Range exceeds entity length: {value}")


class HttpxTransport(Transport):
    """HTTP transport that always goes through a loopback mixed-port."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def head(self, url: str, proxy_port: int) -> HeadInfo:
        with _client(proxy_port, self._timeout) as client:
            try:
                response = client.head(url)
            except httpx.HTTPError as exc:
                raise NodeFailed(f"HEAD request failed: {type(exc).__name__}") from exc
        status = response.status_code
        if status in _THROTTLE_STATUSES:
            raise HttpStatusError(status, f"HEAD returned HTTP {status}")
        if status >= 500:
            raise NodeFailed(f"HEAD returned HTTP {status}")
        if status == 405:
            raise RangeNotSupported("server rejected HEAD with HTTP 405")
        if status >= 400:
            raise HttpStatusError(status, f"HEAD returned HTTP {status}")
        headers = response.headers
        content_length = -1
        raw_length = headers.get("content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                content_length = -1
        return HeadInfo(
            url=url,
            final_url=str(response.url),
            status=status,
            content_length=content_length,
            accept_ranges=_header_contains_bytes(headers.get("accept-ranges", "")),
            etag=headers.get("etag", ""),
            last_modified=headers.get("last-modified", ""),
        )

    def get_range(
        self,
        url: str,
        proxy_port: int,
        start: int,
        end: int,
        *,
        etag: str = "",
        last_modified: str = "",
    ) -> Iterator[bytes]:
        if end < start:
            raise RangeNotSupported(f"invalid range {start}-{end}")
        headers = {"Range": f"bytes={start}-{end}"}
        if etag:
            headers["If-Range"] = etag
        elif last_modified:
            headers["If-Range"] = last_modified
        with _client(proxy_port, self._timeout) as client:
            try:
                with client.stream("GET", url, headers=headers) as response:
                    status = response.status_code
                    if status in _THROTTLE_STATUSES:
                        raise HttpStatusError(status, f"range request returned HTTP {status}")
                    if status >= 500:
                        raise NodeFailed(f"range request returned HTTP {status}")
                    if status != 206:
                        raise RangeNotSupported(f"expected HTTP 206 for a range request, got {status}")
                    _parse_content_range(
                        response.headers.get("content-range", ""), start, end
                    )
                    for chunk in response.iter_bytes():
                        if chunk:
                            yield chunk
            except httpx.HTTPError as exc:
                raise NodeFailed(f"range request failed: {type(exc).__name__}") from exc

    def get_full(self, url: str, proxy_port: int) -> Iterator[bytes]:
        with _client(proxy_port, self._timeout) as client:
            try:
                with client.stream("GET", url) as response:
                    status = response.status_code
                    if status in _THROTTLE_STATUSES:
                        raise HttpStatusError(status, f"GET returned HTTP {status}")
                    if status >= 500:
                        raise NodeFailed(f"GET returned HTTP {status}")
                    if status < 200 or status >= 300:
                        raise HttpStatusError(status, f"GET returned HTTP {status}")
                    for chunk in response.iter_bytes():
                        if chunk:
                            yield chunk
            except httpx.HTTPError as exc:
                raise NodeFailed(f"GET request failed: {type(exc).__name__}") from exc
