"""Icono y menu de bandeja (pystray)."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import Any

import pystray
from PIL import Image

from pr_watch import icon as icon_mod
from pr_watch import theme


class Tray:
    def __init__(
        self,
        *,
        on_toggle: Callable[[], None],
        on_refresh: Callable[[], None],
        on_quit: Callable[[], None],
        on_autostart: Callable[[], None],
        autostart_on: Callable[[], bool],
        autostart_available: bool,
    ) -> None:
        self._renderer = icon_mod.TrayRenderer(64)
        image = self._renderer.render(dark_taskbar=theme.dark_taskbar(), unseen=False)
        assert image is not None
        self._title = "pr-watch"
        self._lock = threading.Lock()
        self.icon: Any = pystray.Icon(
            "pr-watch",
            image,
            self._title,
            menu=pystray.Menu(
                # `default` hace que el clic izquierdo la active en Windows. En
                # escritorios que abren el menu con el clic, es la primera entrada.
                pystray.MenuItem("Abrir pr-watch", lambda: on_toggle(), default=True),
                pystray.MenuItem("Actualizar ahora", lambda: on_refresh()),
                pystray.Menu.SEPARATOR,
                # Marcada segun la entrada real del sistema, consultada cada vez
                # que se abre el menu. Inhabilitada fuera del ejecutable.
                pystray.MenuItem(
                    "Arrancar con la sesión",
                    lambda: on_autostart(),
                    checked=lambda _item: autostart_on(),
                    enabled=autostart_available,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir", lambda: on_quit()),
            ),
        )

    def start(self) -> None:
        """Arranca el icono sin bloquear.

        En Windows, pystray lleva su propio bucle de mensajes en un hilo. En
        Linux el backend comparte el bucle de GTK que ya corre pywebview, asi
        que basta con `run_detached`.
        """
        if sys.platform == "win32":
            threading.Thread(target=self.icon.run, name="tray", daemon=True).start()
        else:
            self.icon.run_detached()

    def update(self, *, unseen: bool, tooltip: str) -> None:
        with self._lock:
            image: Image.Image | None = self._renderer.render(
                dark_taskbar=theme.dark_taskbar(), unseen=unseen
            )
            if image is not None:
                self.icon.icon = image
            # El tooltip de Windows admite 127 caracteres.
            title = tooltip[:127]
            if title != self._title:
                self._title = title
                self.icon.title = title

    def stop(self) -> None:
        self.icon.stop()
