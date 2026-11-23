"""Static defaults shared by configuration and UI code."""

from __future__ import annotations

DEFAULT_BYPASS = (
    "localhost;127.*;10.*;172.16.*;172.17.*;172.18.*;172.19.*;172.20.*;"
    "172.21.*;172.22.*;172.23.*;172.24.*;172.25.*;172.26.*;172.27.*;"
    "172.28.*;172.29.*;172.30.*;172.31.*;192.168.*;*.local;<local>"
)

#: Keys the generator always overwrites on the runtime copy.
MANAGED_KEYS = (
    "external-controller",
    "secret",
    "bind-address",
    "allow-lan",
    "mixed-port",
    "port",
    "socks-port",
    "redir-port",
    "tproxy-port",
    "tun",
    "log-level",
    "profile",
)

#: Upper bound for an imported profile; subscriptions are text files.
MAX_PROFILE_BYTES = 16 * 1024 * 1024

#: Refuse to import files that obviously are not Mihomo configuration.
ALLOWED_PROFILE_SUFFIXES = (".yaml", ".yml")

#: The core release used when the user has no local binary yet.
CORE_RELEASE_TAG = "v1.19.33"
CORE_DOWNLOAD_URL = (
    "https://github.com/MetaCubeX/mihomo/releases/download/"
    f"{CORE_RELEASE_TAG}/mihomo-windows-amd64-{CORE_RELEASE_TAG}.zip"
)
CORE_ASSET_NAME = "mihomo-windows-amd64.exe"
# SHA-256 of the pinned release archive above; verified after every download.
CORE_SHA256 = "6ab2180875f9f6fff8b19386d760daec257f66b45f72b3afc650634272fa837a"
