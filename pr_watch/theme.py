"""Tema de la barra de tareas, para elegir el color del glifo de bandeja."""

from __future__ import annotations

import sys

_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def dark_taskbar() -> bool:
    """True si la barra de tareas es oscura. Fuera de Windows se asume oscura."""
    if sys.platform != "win32":
        return True
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE) as key:
            value, _ = winreg.QueryValueEx(key, "SystemUsesLightTheme")
    except OSError:
        return True
    return value == 0
