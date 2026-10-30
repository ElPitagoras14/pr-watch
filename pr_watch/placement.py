"""Donde aparece el panel: en la esquina del area de trabajo junto a la bandeja.

La geometria (`place`) es pura y se prueba sola. Las consultas al sistema
(posicion del icono, monitor, DPI) estan aisladas abajo, porque dependen de
atributos internos de pystray y de la API de Windows (D9). El rectangulo del
icono ya no decide la posicion del panel: solo sirve para saber en que monitor
dibujarlo.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Any

MARGIN = 8  # pixeles fisicos entre el panel y la barra o el icono


@dataclass(frozen=True, slots=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def center(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2


def taskbar_edge(screen: Rect, work: Rect) -> str:
    """Lado de la pantalla que ocupa la barra: el que el area de trabajo no alcanza."""
    gaps = {
        "bottom": screen.bottom - work.bottom,
        "top": work.top - screen.top,
        "left": work.left - screen.left,
        "right": screen.right - work.right,
    }
    edge, gap = max(gaps.items(), key=lambda kv: kv[1])
    return edge if gap > 0 else "bottom"


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))


def place(size: tuple[int, int], screen: Rect, work: Rect) -> tuple[int, int]:
    """Esquina superior izquierda del panel, en pixeles fisicos.

    Siempre la esquina del area de trabajo donde vive la bandeja: con la barra
    abajo o arriba, la derecha; con la barra en un lateral, la de abajo. Antes
    el panel se centraba sobre el icono, pero el icono rara vez es el ultimo de
    la bandeja y el panel quedaba flotando a media distancia de la esquina.
    """
    w, h = size
    edge = taskbar_edge(screen, work)
    max_x = work.right - w - MARGIN
    max_y = work.bottom - h - MARGIN
    min_x = work.left + MARGIN
    min_y = work.top + MARGIN

    x = min_x if edge == "left" else max_x
    y = min_y if edge == "top" else max_y
    return _clamp(x, min_x, max(min_x, max_x)), _clamp(y, min_y, max(min_y, max_y))


# ---- consultas a Windows ----


def _win() -> Any:
    return ctypes.windll  # type: ignore[attr-defined]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_uint),
        ("guidItem", _GUID),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _rect(r: _RECT) -> Rect:
    return Rect(r.left, r.top, r.right, r.bottom)


def tray_icon_rect(tray_icon: Any) -> Rect | None:
    """Rectangulo del icono de pystray en pantalla, o None si no se puede saber."""
    if sys.platform != "win32":
        return None
    hwnd = getattr(tray_icon, "_hwnd", None)
    if not hwnd:
        return None
    # pystray pasa `hID=id(self)`, pero el campo se llama `uID`: ctypes lo
    # ignora y el icono queda registrado con uID 0. Se prueba ese primero.
    for uid in (0, id(tray_icon) & 0xFFFFFFFF):
        ident = _NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(_NOTIFYICONIDENTIFIER)
        ident.hWnd = hwnd
        ident.uID = uid
        out = _RECT()
        try:
            hr = _win().shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(out))
        except (AttributeError, OSError):
            return None
        if hr == 0 and out.right > out.left:
            return _rect(out)
    return None


def monitor_at(point: tuple[int, int] | None) -> tuple[Rect, Rect, float] | None:
    """(pantalla, area de trabajo, escala) del monitor que contiene el punto."""
    if sys.platform != "win32":
        return None
    user32 = _win().user32
    MONITOR_DEFAULTTOPRIMARY = 1
    MONITOR_DEFAULTTONEAREST = 2
    if point is None:
        hmon = user32.MonitorFromPoint(_POINT(0, 0), MONITOR_DEFAULTTOPRIMARY)
    else:
        hmon = user32.MonitorFromPoint(_POINT(*point), MONITOR_DEFAULTTONEAREST)
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(info)):
        return None
    scale = 1.0
    try:
        dpi_x, dpi_y = ctypes.c_uint(), ctypes.c_uint()
        if (
            _win().shcore.GetDpiForMonitor(
                ctypes.c_void_p(hmon), 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            )
            == 0
        ):
            scale = dpi_x.value / 96
    except (AttributeError, OSError):
        pass
    return _rect(info.rcMonitor), _rect(info.rcWork), scale


def set_window_rect(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    """Coloca una ventana en pixeles fisicos, sin cambiar su orden Z."""
    SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
    _win().user32.SetWindowPos(
        ctypes.c_void_p(hwnd), None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE
    )


def bring_to_front(hwnd: int) -> None:
    user32 = _win().user32
    user32.ShowWindow(ctypes.c_void_p(hwnd), 5)  # SW_SHOW
    user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
