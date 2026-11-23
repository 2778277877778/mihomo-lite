"""Minimal synchronous client for the Mihomo REST API.

The client is synchronous on purpose: every call is cheap and the GUI runs it
from a worker thread, which keeps the dependency surface small (no qasync).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mihomo_lite.utils.exceptions import ApiError

log = logging.getLogger(__name__)


class MihomoAPI:
    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        timeout: float = 5.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._secret = secret
        self._owns_client = client is None
        if client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {secret}"},
                timeout=timeout,
            )
        else:
            self._client = client
            self._client.headers.setdefault("Authorization", f"Bearer {secret}")

    def __enter__(self) -> MihomoAPI:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # -- low level ---------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ApiError(f"core API timed out: {path}") from exc
        except httpx.ConnectError as exc:
            raise ApiError("the Mihomo core API is not reachable") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"core API request failed: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text.strip()[:200]
            raise ApiError(
                f"core API returned HTTP {response.status_code} for {path}"
                + (f": {detail}" if detail else ""),
                status=response.status_code,
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(f"core API returned invalid JSON for {path}") from exc

    # -- endpoints ---------------------------------------------------------
    def version(self) -> dict[str, Any]:
        data = self._request("GET", "/version")
        return data if isinstance(data, dict) else {}

    def configs(self) -> dict[str, Any]:
        data = self._request("GET", "/configs")
        return data if isinstance(data, dict) else {}

    def proxies(self) -> dict[str, Any]:
        data = self._request("GET", "/proxies")
        return data if isinstance(data, dict) else {}

    def connections(self) -> dict[str, Any]:
        data = self._request("GET", "/connections")
        return data if isinstance(data, dict) else {}

    def select_proxy(self, group: str, name: str) -> None:
        self._request("PUT", f"/proxies/{group}", json={"name": name})

    def proxy_delay(self, name: str, url: str, *, timeout_ms: int = 5000) -> int:
        data = self._request(
            "GET",
            f"/proxies/{name}/delay",
            params={"url": url, "timeout": timeout_ms},
        )
        if isinstance(data, dict):
            try:
                return int(data.get("delay", 0))
            except (TypeError, ValueError):
                return 0
        return 0

    def group_delay(self, group: str, url: str, *, timeout_ms: int = 5000) -> dict[str, int]:
        data = self._request(
            "GET",
            f"/group/{group}/delay",
            params={"url": url, "timeout": timeout_ms},
        )
        result: dict[str, int] = {}
        if isinstance(data, dict):
            for key, value in data.items():
                try:
                    result[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue
        return result

    def set_mode(self, mode: str) -> None:
        mode = mode.lower()
        if mode not in {"rule", "global", "direct"}:
            raise ApiError(f"unsupported outbound mode: {mode}")
        self._request("PATCH", "/configs", json={"mode": mode})

    def close_connections(self) -> None:
        self._request("DELETE", "/connections")

    def reload_config(self, path: str) -> None:
        self._request("PUT", "/configs", json={"path": path, "force": True})
