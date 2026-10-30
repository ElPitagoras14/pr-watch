"""Punto de entrada: `python -m pr_watch` o el ejecutable empaquetado."""

from __future__ import annotations

import logging
import os
import sys

from pr_watch import __version__, config, log, platform_check
from pr_watch.single_instance import AcquireResult, Guard, ask_first_to_show, notify_user

_log = logging.getLogger("pr_watch")


def main() -> int:
    config_dir = config.config_dir()
    log.setup(config_dir, level=logging.DEBUG if os.environ.get("PR_WATCH_DEBUG") else logging.INFO)
    _log.info("pr-watch %s arrancando", __version__)

    problem = platform_check.check()
    if problem:
        print(problem, file=sys.stderr)
        return 1
    if "--check-system" in sys.argv[1:]:
        # Diagnostico (y prueba de arranque del pipeline): sin instancia unica ni bandeja.
        print("pr-watch: las bibliotecas del sistema estan completas")
        return 0

    guard = Guard(config_dir)
    result = guard.acquire()
    if result is AcquireResult.FAILED:
        _log.error("No se pudo comprobar si ya hay otra instancia en marcha; no arrancamos")
        notify_user(
            "pr-watch no pudo comprobar si ya esta en marcha y no arrancara, "
            "para evitar correr dos instancias a la vez sin saberlo. "
            "Revisa el registro o reinicia sesion si el problema persiste."
        )
        return 1
    if result is AcquireResult.ALREADY_RUNNING:
        _log.info("Ya hay una instancia: se le pide que muestre su panel")
        if not ask_first_to_show(config_dir):
            _log.warning("No se pudo avisar a la instancia en marcha")
            notify_user(
                "pr-watch ya esta en marcha pero no responde. "
                "Cierra el proceso manualmente si el problema persiste."
            )
        return 0

    from pr_watch.app import App

    App(config_dir, guard).run()
    _log.info("pr-watch terminado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
