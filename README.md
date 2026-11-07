# Mihomo Lite

**Simple. Lightweight. Reliable.**

A small Windows GUI client for the [Mihomo](https://github.com/MetaCubeX/mihomo) proxy core.
It does one thing well: start the core, switch nodes, use the Windows system proxy, and
put everything back when you quit.

> Working title. The name is not final; trademark availability will be checked before release.

![Dashboard](docs/images/dashboard.png)

## Why another client?

- **Simple** - connect, pick a node, disconnect. Nothing else in the way.
- **Lightweight** - PySide6 Essentials only (no WebEngine/QML), no background service,
  no TUN driver. The ~58 MB core is bundled, so there is nothing to download on first run.
- **Reliable** - the previous system proxy settings are saved before they are touched and
  restored on disconnect, on crash, and on the next start after a crash.
- **Open** - MIT licensed application code, small enough to read in an afternoon.

## Features (v0.1)

- Ships with a verified Mihomo core (unmodified, GPL-3.0) - works offline after install
- Local YAML profile import and subscription import/update with backup + validation
- Start/stop the Mihomo core with QProcess and surface its output in the UI
- Windows system proxy handling (WinINET per-connection API + registry mirror)
- Crash-safe proxy journal: restores your original setting after a crash
- Proxy groups and node switching, latency tests
- Live upload/download speed from the Mihomo WebSocket
- Tray icon, start-with-Windows, single-instance guard
- Frameless rounded window with frosted-glass surfaces (Windows acrylic blur) in dark and light

Not in v0.1: TUN mode, rule editing, connection list, multi-core support.

## Install

1. Download the latest installer from the Releases page (or build it yourself, below).
2. On first run, import a YAML profile (file or subscription).
3. Press **Connect**.

The installer includes a Mihomo core, so no download is needed. **Settings -> Mihomo core**
shows which binary is in use and lets you download a newer official build or point at your
own mihomo.exe.

## Requirements

- Windows 10/11 x64
- A Mihomo configuration file (Clash/Mihomo YAML)
- For development: Python 3.11+ (3.12 recommended)

## Development

~~~powershell
git clone https://github.com/your-name/mihomo-lite.git
cd mihomo-lite
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

python -m mihomo_lite   # run the app
pytest                  # tests
ruff check src tests    # lint
~~~

Headless checks used during development:

~~~powershell
python tools/smoke/ui_smoke.py       # renders every page to tools/smoke/*.png
python tools/smoke/e2e_connect.py    # real core + fake system proxy, connect/disconnect
~~~

## Build a Windows package

~~~powershell
python scripts/build_windows.py               # PyInstaller onedir -> dist/MihomoLite
python scripts/build_windows.py --installer   # plus Inno Setup installer (needs ISCC)
~~~

The packaged app still downloads the core on demand, so the installer stays small.

## How it works

~~~text
PySide6 UI  ->  ConnectionManager  ->  MihomoProcess / MihomoAPI / SystemProxy
                                          |
                                    Mihomo core (separate process)
~~~

- The UI never talks to the core directly; it observes one state machine.
- The originally imported YAML is never modified. A hardened runtime copy is generated
  with a localhost-only controller, a fresh random secret, TUN disabled and a random port.
- The system proxy is journalled before it is changed; a leftover journal is replayed on
  the next start if the owning process is gone.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md),
[docs/USER_GUIDE.md](docs/USER_GUIDE.md),
[docs/FEASIBILITY.md](docs/FEASIBILITY.md).

## License

Application code: MIT (see [LICENSE](LICENSE)).
Mihomo core: GPL-3.0, bundled unmodified; source and notices in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and licenses/.
PySide6 / Qt: LGPL-3.0, dynamically linked.

## Contributing

Issues and pull requests are welcome. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) first.
