"""Una sola instancia por usuario; la segunda pide a la primera su panel (D14)."""

from __future__ import annotations

import contextlib
import ctypes
import getpass
import logging
import os
import secrets
import sys
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_MUTEX_NAME = "Local\\pr-watch"
_ERROR_ALREADY_EXISTS = 183
_SHOW = "show"


def _address(config_dir: Path) -> str:
    if sys.platform == "win32":
        user = "".join(c for c in getpass.getuser() if c.isalnum()) or "user"
        return rf"\\.\pipe\pr-watch-{user}"
    return str(config_dir / "instance.sock")


def _authkey(config_dir: Path) -> bytes:
    """Clave compartida en un archivo solo legible por el usuario."""
    path = config_dir / "instance.key"
    try:
        return bytes.fromhex(path.read_text("ascii").strip())
    except (OSError, ValueError):
        pass
    key = secrets.token_bytes(32)
    config_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, key.hex().encode("ascii"))
    finally:
        os.close(fd)
    return key


class Guard:
    """Mantiene el candado de instancia mientras viva el objeto."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir
        self._handle: Any = None
        self._listener: Listener | None = None

    def acquire(self) -> bool:
        """True si somos la primera instancia."""
        if sys.platform == "win32":
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
            if kernel32.GetLastError() == _ERROR_ALREADY_EXISTS:
                return False
            self._handle = handle
            return True
        import fcntl

        self.config_dir.mkdir(parents=True, exist_ok=True)
        f = open(self.config_dir / "instance.lock", "w")  # noqa: SIM115
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self._handle = f
        return True

    def serve(self, on_show: Callable[[], None]) -> None:
        """Escucha a las instancias siguientes en un hilo propio."""
        address = _address(self.config_dir)
        if sys.platform != "win32":
            with contextlib.suppress(FileNotFoundError):
                os.unlink(address)
        try:
            self._listener = Listener(address, authkey=_authkey(self.config_dir))
        except OSError as e:
            _log.warning("No se pudo abrir el canal de instancia unica: %s", e)
            return

        listener = self._listener

        def loop() -> None:
            while True:
                try:
                    with listener.accept() as conn:
                        if conn.recv() == _SHOW:
                            on_show()
                except (OSError, EOFError):
                    # Un cliente que se fue a mitad. La pausa evita un bucle
                    # caliente si el canal dejara de aceptar.
                    time.sleep(0.2)
                except Exception as e:  # autenticacion fallida u otro cliente
                    _log.warning("Peticion de instancia rechazada: %s", type(e).__name__)

        threading.Thread(target=loop, name="single-instance", daemon=True).start()


def ask_first_to_show(config_dir: Path) -> bool:
    try:
        with Client(_address(config_dir), authkey=_authkey(config_dir)) as conn:
            conn.send(_SHOW)
        return True
    except Exception as e:
        _log.warning("No se pudo avisar a la instancia en marcha: %s", type(e).__name__)
        return False
