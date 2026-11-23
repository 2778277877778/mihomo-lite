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

## Wintun (bundled binary)

- Project: https://www.wintun.net
- Version bundled at build time: 0.14.1 (unmodified, SHA-256 verified by the build)
- License: GNU General Public License v2.0 (full text in licenses/wintun-GPL-2.0.txt)
- The DLL is placed next to the Mihomo core (runtime/wintun.dll) and loaded by the core when
  TUN mode is enabled. It is redistributed unmodified; the corresponding source is available
  from the upstream project at https://www.wintun.net/.

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
