"""Public-IP lookup and download speed measurement through the local proxy."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

IP_ENDPOINTS = (
    "https://api.ip.sb/ip",
    "https://ifconfig.me/ip",
    "https://ipinfo.io/ip",
)
SPEED_ENDPOINT = "https://speed.cloudflare.com/__down?bytes=25000000"
_MAX_SECONDS = 6.0
_MAX_BYTES = 30 * 1024 * 1024


@dataclass(frozen=True)
class IpResult:
    address: str
    source: str


def _proxy_url(server: str | None) -> str | None:
    return f"http://{server}" if server else None


def fetch_public_ip(server: str | None, *, timeout: float = 8.0) -> IpResult:
    """Return the public IP as seen through *server* (or directly if None)."""
    last_error = "no endpoint answered"
    with httpx.Client(
        proxy=_proxy_url(server),
        timeout=timeout,
        follow_redirects=True,
        trust_env=False,
    ) as client:
        for url in IP_ENDPOINTS:
            try:
                response = client.get(url)
                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}"
                    continue
                text = response.text.strip()
                if 0 < len(text) <= 64 and "\n" not in text:
                    return IpResult(address=text, source=url.split("/")[2])
                last_error = "unexpected response"
            except httpx.HTTPError as exc:
                last_error = str(exc)
    raise RuntimeError(f"could not detect the public IP: {last_error}")


def speed_mbps(total_bytes: int, seconds: float) -> float:
    if total_bytes <= 0 or seconds <= 0:
        return 0.0
    return (total_bytes * 8) / seconds / 1_000_000


def measure_download(
    server: str | None,
    *,
    url: str = SPEED_ENDPOINT,
    max_seconds: float = _MAX_SECONDS,
) -> float:
    """Download for a few seconds and return the average speed in Mbit/s."""
    total = 0
    started = time.monotonic()
    try:
        with httpx.Client(
            proxy=_proxy_url(server),
            timeout=httpx.Timeout(10.0, read=15.0),
            follow_redirects=True,
            trust_env=False,
        ) as client, client.stream("GET", url) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(chunk_size=64 * 1024):
                total += len(chunk)
                if total >= _MAX_BYTES or time.monotonic() - started >= max_seconds:
                    break
    except httpx.HTTPError as exc:
        raise RuntimeError(f"speed test failed: {exc}") from exc
    return speed_mbps(total, max(time.monotonic() - started, 0.001))
