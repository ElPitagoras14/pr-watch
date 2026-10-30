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

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    from pystray._util import win32

    # pystray no publica tipos: para el comprobador la base es `object` y todos
    # sus atributos internos serian errores. Declararla `Any` lo evita sin
    # apagar la comprobacion del resto del modulo.
    _PystrayIcon: Any = pystray.Icon

    def _force_foreground(hwnd: int) -> None:
        """Pone `hwnd` en primer plano aunque Windows se resista.

        `SetForegroundWindow` falla en silencio si el proceso no recibio la
        ultima entrada del usuario, y eso depende de como se lanzo: desde una
        terminal funciona, con doble clic en el Explorador no. Sin primer plano
        el menu se dibuja pero no resalta la opcion bajo el raton. Enlazar la
        cola de entrada con la del hilo en primer plano lo permite.
        """
        user32 = ctypes.windll.user32
        mine = ctypes.windll.kernel32.GetCurrentThreadId()
        front = user32.GetForegroundWindow()
        theirs = user32.GetWindowThreadProcessId(front, None) if front else 0
        attached = bool(theirs and theirs != mine and user32.AttachThreadInput(mine, theirs, True))
        try:
            win32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(mine, theirs, False)

    class WindowsIcon(_PystrayIcon):
        """pystray abre el menu sobre una ventana distinta de la que pone delante.

        `Icon._run` crea dos ventanas, `_hwnd` y `_menu_hwnd`. Antes de abrir el
        menu, pystray llama a `SetForegroundWindow(_hwnd)` pero pasa
        `_menu_hwnd` como duena del menu (`_win32.py:206` y `:221`). Windows
        exige que la duena del menu sea la ventana de primer plano: si no lo es,
        el menu se dibuja pero no sigue al raton ni acepta clics, y
        `TrackPopupMenuEx` devuelve 0 sin invocar nada.

        Con pystray solo en el hilo principal el descuido no se nota. Aqui, con
        el bucle de mensajes de WinForms que levanta pywebview en el hilo
        principal y la bandeja en otro, el menu queda muerto: ni «Abrir
        pr-watch» ni «Salir» hacian nada.
        """

        def _on_notify(self, wparam: int, lparam: int) -> None:
            if lparam != win32.WM_RBUTTONUP or not self._menu_handle:
                super()._on_notify(wparam, lparam)
                return

            _force_foreground(self._menu_hwnd)
            point = wintypes.POINT()
            win32.GetCursorPos(ctypes.byref(point))
            hmenu, descriptors = self._menu_handle
            index = win32.TrackPopupMenuEx(
                hmenu,
                win32.TPM_RIGHTALIGN | win32.TPM_BOTTOMALIGN | win32.TPM_RETURNCMD,
                point.x,
                point.y,
                self._menu_hwnd,
                None,
            )
            # KB135788: sin este mensaje el menu puede quedarse abierto cuando se
            # descarta haciendo clic fuera.
            win32.PostMessage(self._menu_hwnd, 0x0000, 0, 0)  # WM_NULL
            if index > 0:
                descriptors[index - 1](self)

    Icon: Any = WindowsIcon
else:
    Icon = pystray.Icon


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
        self.icon: Any = Icon(
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
