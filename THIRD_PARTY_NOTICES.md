# Third-party notices

Mihomo Lite is MIT licensed (see LICENSE). It redistributes the following third-party
components; their licenses apply to those components, not to the application code.

## Mihomo core (bundled binary)

- Project: https://github.com/MetaCubeX/mihomo
- Version bundled at build time: v1.19.33 (see pyproject/CHANGELOG of the release)
- License: GNU General Public License v3.0 (full text in licenses/mihomo-GPL-3.0.txt)
- Redistribution: the binary is shipped **unmodified**. The complete corresponding source
  for this exact version is available from the upstream repository and release page:

  - source: https://github.com/MetaCubeX/mihomo/tree/v1.19.33
  - release: https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.33

  If you redistribute Mihomo Lite, keep this notice, the GPL-3.0 text and the version
  information together with the binary, and keep the source availability above intact.

The application communicates with the core as a separate process over a loopback HTTP
API; the two are distributed together as an aggregate and are not linked into one program.

## Wintun (optional, downloaded at runtime)

- Project: https://www.wintun.net
- License: GPL-2.0 (see the upstream distribution)
- Not bundled with Mihomo Lite. When the user enables TUN mode, Settings can download the
  official build and place wintun.dll next to the core; it is used by Mihomo as a driver.

## PySide6 / Qt

- https://www.qt.io/qt-for-python
- License: LGPL-3.0 (dynamic linking, unmodified Qt libraries; users may replace the Qt DLLs
  shipped next to the executable)
- Qt libraries are distributed inside the onedir package; their license texts are stored in
  the package under licenses/qt-LGPL-3.0.txt when bundled by Qt's hooks.

## Python runtime and libraries

- Python (PSF-2.0), httpx (BSD-3-Clause), httpcore (BSD-3-Clause), h11 (MIT),
  anyio (MIT), certifi (MPL-2.0), idna (BSD-3-Clause), websockets (BSD-3-Clause),
  PyYAML (MIT), pydantic / pydantic-core (MIT), annotated-types (MIT),
  typing-inspection (MIT), typing_extensions (PSF-2.0), colorama (BSD-3-Clause).

Exact pinned versions are listed in pyproject.toml and reproducible from the build
environment described in docs/DEVELOPMENT.md.
