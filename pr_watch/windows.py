"""Ventanas pywebview: el panel y los ajustes, y la API que ven desde JS (D7).

La logica de cuando mostrar u ocultar vive en `PanelLogic`, sin ventanas, para
poder probarla. Lo que toca pywebview y Win32 esta en `NativeWindow`.
"""

from __future__ import annotations

import ctypes
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pr_watch import placement

if TYPE_CHECKING:
    from pr_watch.app import App

_log = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"
PANEL_WIDTH = 340
SETTINGS_WIDTH = 400

# Un clic en el icono con el panel abierto quita primero el foco al panel (que
# se oculta) y luego llega el clic, que lo volveria a abrir. Este margen
# distingue ese caso de una apertura de verdad.
REOPEN_GUARD_SECS = 0.35


@dataclass(slots=True)
class PanelLogic:
    visible: bool = False
    pinned: bool = False
    settings_open: bool = False
    hidden_by_blur_at: float = field(default=-1e9)

    def toggle(self, now: float) -> str:
        """'show', 'hide' o 'ignore' ante una activacion del icono."""
        if self.visible:
            return "hide"
        if now - self.hidden_by_blur_at < REOPEN_GUARD_SECS:
            return "ignore"
        return "show"

    def on_blur(self, now: float) -> bool:
        """True si hay que ocultar el panel al perder el foco."""
        if not self.visible or self.pinned or self.settings_open:
            return False
        self.hidden_by_blur_at = now
        return True

    def shown(self) -> None:
        self.visible = True

    def hidden(self) -> None:
        self.visible = False
        # El fijado no se hereda entre aperturas.
        self.pinned = False


class NativeWindow:
    """Ayudas sobre una ventana de pywebview que necesitan el handle nativo."""

    def __init__(self, window: Any) -> None:
        self.window = window

    def hwnd(self) -> int | None:
        native = getattr(self.window, "native", None)
        if native is None or sys.platform != "win32":
            return None
        try:
            return int(native.Handle.ToInt64())
        except Exception:
            return None

    def hide_from_taskbar(self) -> None:
        """Ventana de herramientas: sin boton en la barra de tareas ni en Alt+Tab."""
        hwnd = self.hwnd()
        if hwnd is None:
            return
        GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        style = user32.GetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        user32.SetWindowLongPtrW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, ctypes.c_ssize_t(style))

    def place(
        self, logical_size: tuple[int, int], anchor_icon: Any | None, *, near: str = "tray"
    ) -> None:
        """Coloca la ventana junto al icono (o en la esquina), en pixeles fisicos."""
        hwnd = self.hwnd()
        if hwnd is None:
            self._place_logical(logical_size)
            return
        anchor = placement.tray_icon_rect(anchor_icon) if anchor_icon is not None else None
        # Sin icono localizable, el monitor principal: es el que lleva la bandeja.
        point = anchor.center() if anchor else None
        mon = placement.monitor_at(point)
        if mon is None:
            self._place_logical(logical_size)
            return
        screen, work, scale = mon
        size = (round(logical_size[0] * scale), round(logical_size[1] * scale))
        if near == "tray":
            x, y = placement.place(size, screen, work, anchor)
        else:
            cx, cy = work.center()
            x, y = cx - size[0] // 2, cy - size[1] // 2
        _log.debug(
            "Colocacion: icono=%s punto=%s pantalla=%s trabajo=%s escala=%s -> %s",
            anchor,
            point,
            screen,
            work,
            scale,
            (x, y, *size),
        )
        placement.set_window_rect(hwnd, x, y, size[0], size[1])

    def _place_logical(self, logical_size: tuple[int, int]) -> None:
        # Fuera de Windows no se sabe donde esta el icono: esquina superior
        # derecha de la pantalla principal, donde suele vivir la bandeja.
        import webview

        w, h = logical_size
        self.window.resize(w, h)
        try:
            screen = webview.screens[0]
            self.window.move(max(0, screen.width - w - 12), 40)
        except Exception:
            pass

    def front(self) -> None:
        hwnd = self.hwnd()
        if hwnd is not None:
            placement.bring_to_front(hwnd)


def push(window: Any, function: str, payload: Any) -> None:
    """Llama a una funcion JS con un dict. json.dumps produce un literal JS
    valido, asi que ningun titulo de PR puede inyectar codigo."""
    script = f"window.{function} && window.{function}({json.dumps(payload, ensure_ascii=False)})"
    try:
        window.run_js(script)
    except Exception as e:
        _log.debug("No se pudo actualizar la ventana: %s", e)


class PanelApi:
    """Lo que el JS del panel puede pedir. Metodos pequenos; Python decide."""

    def __init__(self, app: App) -> None:
        self._app = app

    def ready(self) -> None:
        self._app.panel_ready()

    def refresh(self) -> None:
        self._app.refresh()

    def open_url(self, url: str) -> None:
        self._app.open_url(str(url))

    def toggle_pin(self) -> None:
        self._app.toggle_pin()

    def hide(self) -> None:
        self._app.hide_panel()

    def open_settings(self) -> None:
        self._app.open_settings()

    def blur(self) -> None:
        self._app.panel_blur(time.monotonic())

    def content_height(self, height: int) -> None:
        self._app.panel_height(int(height))


class SettingsApi:
    def __init__(self, app: App) -> None:
        self._app = app

    def settings_load(self) -> dict[str, Any]:
        return self._app.settings_load()

    def settings_verify_token(self, forge: dict[str, Any], token: str) -> dict[str, Any]:
        return self._app.settings_verify_token(dict(forge or {}), str(token or ""))

    def settings_verify(self, forge: dict[str, Any], scope: str, token: str) -> dict[str, Any]:
        return self._app.settings_verify(dict(forge or {}), str(scope or ""), str(token or ""))

    def settings_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._app.settings_save(dict(payload or {}))

    def settings_logout(self) -> dict[str, Any]:
        return self._app.settings_logout()

    def settings_close(self) -> None:
        self._app.close_settings()

    def open_url(self, url: str) -> None:
        self._app.open_url(str(url))

    def open_create_token(self, forge: dict[str, Any]) -> None:
        self._app.open_create_token(dict(forge or {}))

    def open_config_file(self) -> None:
        self._app.open_config_file()

    def content_height(self, height: int) -> None:
        self._app.settings_height(int(height))


def ui_url(name: str) -> str:
    return str(UI_DIR / name)
