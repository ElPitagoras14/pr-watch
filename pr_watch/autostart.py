"""Arranque con la sesion del usuario, a eleccion suya (como usage-monitor).

Windows: un valor en la clave `Run` del usuario. Linux: un `.desktop` en
`~/.config/autostart`. Nada a nivel de maquina. Viene apagado y solo se
activa desde el menu de bandeja. La propia entrada del sistema es la unica
fuente de verdad: si el usuario la borra a mano, el menu lo refleja.

Desde el codigo fuente no se ofrece: dejaria la sesion apuntando a un
interprete y a un directorio de trabajo del desarrollador.
"""

from __future__ import annotations

import contextlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "pr-watch"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def command_for(executable: str) -> str:
    return f'"{executable}"'


def desktop_entry(exe: str) -> str:
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=pr-watch\n"
        "Comment=Pull requests de GitHub que te involucran, en la bandeja\n"
        f"Exec={command_for(exe)}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _default_autostart_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart"


@dataclass(slots=True)
class Autostart:
    """Acceso a la entrada de autoarranque. Las operaciones lanzan OSError."""

    frozen: bool = field(default_factory=is_frozen)
    executable: str = field(default_factory=lambda: sys.executable)
    platform: str = sys.platform
    run_key: str = RUN_KEY
    autostart_dir: Path = field(default_factory=_default_autostart_dir)

    @property
    def available(self) -> bool:
        return self.frozen

    @property
    def wanted(self) -> str:
        if self.platform == "win32":
            return command_for(self.executable)
        return desktop_entry(self.executable)

    @property
    def desktop_file(self) -> Path:
        return self.autostart_dir / f"{APP_NAME}.desktop"

    # ---- lectura ----

    def current(self) -> str | None:
        """Lo que hay registrado ahora mismo, o None."""
        if self.platform == "win32":
            import winreg

            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.run_key) as key:
                    value, _ = winreg.QueryValueEx(key, APP_NAME)
            except FileNotFoundError:
                return None
            return str(value)
        try:
            return self.desktop_file.read_text("utf-8")
        except FileNotFoundError:
            return None

    def is_enabled(self) -> bool:
        try:
            return self.current() is not None
        except OSError:
            return False

    # ---- escritura ----

    def enable(self) -> None:
        if not self.available:
            raise OSError("el autoarranque solo esta disponible en el ejecutable")
        if self.current() == self.wanted:
            return
        if self.platform == "win32":
            import winreg

            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER, self.run_key, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, self.wanted)
        else:
            self.autostart_dir.mkdir(parents=True, exist_ok=True)
            self.desktop_file.write_text(self.wanted, "utf-8")

    def disable(self) -> None:
        if self.platform == "win32":
            import winreg

            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, self.run_key, 0, winreg.KEY_SET_VALUE
                ) as key:
                    winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        else:
            with contextlib.suppress(FileNotFoundError):
                self.desktop_file.unlink()

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self.enable()
        else:
            self.disable()

    def refresh(self) -> bool:
        """Al arrancar: si esta activado y la ruta cambio, la actualiza.

        Devuelve True si reescribio la entrada. Nunca la crea si no existia.
        """
        if not self.available:
            return False
        current = self.current()
        if current is None or current == self.wanted:
            return False
        self.enable()
        return True
