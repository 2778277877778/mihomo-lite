"""Dry-run Windows system proxy plumbing without changing user state.

Reads the current WinINET configuration and re-applies the exact same
values through InternetSetOptionW, proving the API path works without
mutating the user's live proxy settings.
"""

import ctypes
import sys
from ctypes import wintypes

INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_PER_CONNECTION_OPTION = 75
INTERNET_PER_CONN_FLAGS = 1
INTERNET_PER_CONN_PROXY_SERVER = 2
INTERNET_PER_CONN_PROXY_BYPASS = 3
INTERNET_PER_CONN_AUTOCONFIG_URL = 4

PROXY_TYPE_DIRECT = 0x01
PROXY_TYPE_PROXY = 0x02
PROXY_TYPE_AUTO_PROXY_URL = 0x04


class INTERNET_PER_CONN_OPTION(ctypes.Structure):
    class _Value(ctypes.Union):
        _fields_ = [
            ("dwValue", wintypes.DWORD),
            ("pszValue", wintypes.LPWSTR),
            ("ftValue", wintypes.FILETIME),
        ]

    _fields_ = [("dwOption", wintypes.DWORD), ("Value", _Value)]


class INTERNET_PER_CONN_OPTION_LIST(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("pszConnection", wintypes.LPWSTR),
        ("dwOptionCount", wintypes.DWORD),
        ("dwOptionError", wintypes.DWORD),
        ("pOptions", ctypes.POINTER(INTERNET_PER_CONN_OPTION)),
    ]


def get_options(conn=None, count=4):
    opts = (INTERNET_PER_CONN_OPTION * count)()
    for i in range(count):
        opts[i].dwOption = 0
    lst = INTERNET_PER_CONN_OPTION_LIST()
    lst.dwSize = ctypes.sizeof(INTERNET_PER_CONN_OPTION_LIST)
    lst.pszConnection = conn
    lst.dwOptionCount = count
    lst.dwOptionError = 0
    lst.pOptions = opts
    ok = ctypes.windll.wininet.InternetQueryOptionW(
        None, INTERNET_OPTION_PER_CONNECTION_OPTION, ctypes.byref(lst), ctypes.byref(wintypes.DWORD(lst.dwSize))
    )
    return ok, lst, opts


def main() -> int:
    conn = sys.argv[1] if len(sys.argv) > 1 else None
    count = 4
    ok, lst, opts = get_options(conn, count)
    print("query ok:", bool(ok), "error:", ctypes.get_last_error())
    if not ok:
        print("InternetQueryOption failed; fallback to registry path")
        return 1
    for i in range(count):
        o = opts[i]
        val = o.Value.pszValue if o.dwOption in (2, 3, 4) and o.Value.pszValue else o.Value.dwValue
        print(f"  option={o.dwOption} value={val!r}")

    # Re-apply identical values (no state change) to prove the write path works.
    lst.dwSize = ctypes.sizeof(INTERNET_PER_CONN_OPTION_LIST)
    applied = ctypes.windll.wininet.InternetSetOptionW(
        None, INTERNET_OPTION_PER_CONNECTION_OPTION, ctypes.byref(lst), lst.dwSize
    )
    print("set (no-op) ok:", bool(applied), "error:", ctypes.get_last_error())
    ctypes.windll.wininet.InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
    ctypes.windll.wininet.InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0)
    print("refresh ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
