"""Entry point used by both 'python -m mihomo_lite' and the packaged exe."""

from __future__ import annotations

import sys


def main() -> int:
    from mihomo_lite.app import main as app_main

    return app_main(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
