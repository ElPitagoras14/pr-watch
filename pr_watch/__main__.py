"""Punto de entrada: `python -m pr_watch` o el ejecutable empaquetado."""

from __future__ import annotations

import logging
import os
import sys

from pr_watch import __version__, config, log, platform_check
from pr_watch.single_instance import Guard, ask_first_to_show

_log = logging.getLogger("pr_watch")


def main() -> int:
    config_dir = config.config_dir()
    log.setup(config_dir, level=logging.DEBUG if os.environ.get("PR_WATCH_DEBUG") else logging.INFO)
    _log.info("pr-watch %s arrancando", __version__)

    missing = platform_check.missing_libraries()
    if missing:
        platform_check.report(missing)
        return 1

    guard = Guard(config_dir)
    if not guard.acquire():
        _log.info("Ya hay una instancia: se le pide que muestre su panel")
        ask_first_to_show(config_dir)
        return 0

    from pr_watch.app import App

    App(config_dir, guard).run()
    _log.info("pr-watch terminado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
