"""Local port helpers."""

from __future__ import annotations

import socket

# Ports commonly used by other proxy clients; avoided by default so that
# Mihomo Lite can coexist with an already-running client.
RESERVED_PORTS = frozenset({7890, 7891, 7892, 7897, 9090, 9091, 2019})


def local_ip() -> str:
    """Best-effort LAN address, ignoring tun/fake-ip and link-local ranges."""
    import socket as _socket

    def usable(address: str) -> bool:
        return bool(address) and not address.startswith(
            ("127.", "169.254.", "198.18.", "198.19.")
        )

    try:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidate = str(sock.getsockname()[0])
        if usable(candidate):
            return candidate
    except OSError:
        pass

    try:
        _, _, addresses = _socket.gethostbyname_ex(_socket.gethostname())
    except OSError:
        return "-"
    candidates = [address for address in addresses if usable(address)]
    private = [
        address
        for address in candidates
        if address.startswith(("192.168.", "10.", "172."))
    ]
    if private:
        return private[0]
    return candidates[0] if candidates else "-"


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(preferred: int = 0, *, avoid: set[int] | None = None) -> int:
    """Return a free localhost port, preferring *preferred* when possible."""
    blocked = set(avoid or ()) | RESERVED_PORTS
    if preferred and preferred not in blocked and is_port_free(preferred):
        return preferred

    for _ in range(32):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        if port not in blocked and is_port_free(port):
            return port
    raise OSError("no free local port available")
