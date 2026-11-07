# Development

## Environment

- Windows 10/11 x64
- Python 3.11 or 3.12 (3.12 is what CI and local builds use)
- Git

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
~~~

PySide6-Essentials is enough; do not install the full PySide6 meta package, it drags in
WebEngine and roughly triples the footprint.

## Running

~~~powershell
python -m mihomo_lite            # normal start
python -m mihomo_lite --debug    # verbose console logging
python -m mihomo_lite --hidden   # start in the tray
~~~

Data lives in %LOCALAPPDATA%\MihomoLite (profiles, runtime, logs, core).
Set MIHOMO_LITE_HOME to redirect it, which is what the tests and smoke scripts do.

## Tests

~~~powershell
$env:QT_QPA_PLATFORM = "offscreen"
pytest
ruff check src tests
~~~

The suite never touches the real Windows proxy: system proxy tests use an in-memory backend,
and the connection tests use a fake process, fake API and fake traffic socket.

## Headless smoke checks

These are not part of pytest because they need a real core binary:

~~~powershell
# 1. render every page to tools/smoke/ui_*.png
$env:QT_QPA_FONTDIR = "C:\Windows\Fonts"
python tools/smoke/ui_smoke.py

# 2. real core + fake system proxy, full connect/disconnect cycle
python tools/smoke/e2e_connect.py
~~~

e2e_connect expects tools/core/extracted/mihomo-windows-amd64.exe. Download the archive from
the Mihomo releases page and extract it there (tools/core is git-ignored).

## Packaging

~~~powershell
python scripts/build_windows.py                # dist/MihomoLite (onedir, core bundled)
python scripts/build_windows.py --installer    # + installer via Inno Setup
python scripts/build_windows.py --no-core      # skip the core (network-free build)

The build needs the core once: it uses tools/core/ if present, otherwise downloads the
pinned release (v1.19.33, ~22 MB). The binary is copied to dist/MihomoLite/runtime/mihomo.exe
and is never committed to git. Licenses and THIRD_PARTY_NOTICES.md are copied alongside.
~~~

Use onedir, not onefile: onefile unpacks Qt to a temp folder on every launch, which is slow
and a common antivirus false-positive trigger.

For a reproducible build, use a clean environment that only has the runtime dependencies
(PySide6-Essentials, not the full PySide6 meta package):

~~~powershell
py -3.12 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install PySide6-Essentials httpx websockets PyYAML pydantic pyinstaller
.\.build-venv\Scripts\python.exe -m pip install --no-deps .
.\.build-venv\Scripts\python.exe scripts\build_windows.py
~~~

The frozen executable supports a hidden self test that constructs the whole UI without
showing a window manager session:

~~~powershell
.\dist\MihomoLite\MihomoLite.exe --selftest
~~~

The installer script is packaging/installer.iss; it expects Inno Setup 6 on the machine
(iscc.exe on PATH or in Program Files).

## Debugging notes

- If the core starts but the API never answers, check that the generated config has the
  expected external-controller and that no other client owns the chosen port.
- A stuck "starting" state usually means the QProcess died without emitting finished; look
  at the Logs page, it shows merged stdout/stderr.
- QProcess.terminate() does not reliably stop a console child on Windows; the wrapper falls
  back to kill after 1.2 s. That is expected, not a bug.
- PySide6 keeps only a weak reference to plain Python callables used as slots. TaskRunner
  holds callback references for exactly this reason; do the same if you add callbacks.
- Every ctypes Win32 function in this repo declares argtypes/restype. Keep it that way.
- QApplication must exist before anything calls processEvents or creates widgets; a missing
  instance silently drops queued signals (this cost an hour once).

## Code style

- ruff with the configured rule set; no long lines but formatting is manual (no black).
- Type hints on public functions.
- Keep UI text short and in English; comments explain why, not what.
- Never log secrets; use utils.logger.register_secret for tokens.

## Release checklist

1. pytest green, ruff clean.
2. Version bumped in src/mihomo_lite/__init__.py and pyproject.toml.
3. Build the installer on a clean Windows VM and test install/uninstall.
4. Verify system proxy is restored after killing the app with Task Manager.
5. Tag, publish release, attach installer + SHA256.
