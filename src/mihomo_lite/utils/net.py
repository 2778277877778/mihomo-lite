"""Local port helpers."""

from __future__ import annotations

import socket

# Ports commonly used by other proxy clients; avoided by default so that
# Mihomo Lite can coexist with an already-running client.
RESERVED_PORTS = frozenset({7890, 7891, 7892, 7897, 9090, 9091, 2019})


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
