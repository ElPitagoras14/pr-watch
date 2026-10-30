"""Una sola instancia por usuario; la segunda pide a la primera su panel (D14)."""

from __future__ import annotations

import contextlib
import ctypes
import enum
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
_ERROR_ACCESS_DENIED = 5
_SHOW = "show"


class AcquireResult(enum.Enum):
    """Resultado de `Guard.acquire()`, distinguiendo los dos tipos de fallo."""

    ACQUIRED = "acquired"
    # Ya hay una instancia corriendo (incluye el mutex creado por un proceso
    # con otro contexto de seguridad, p.ej. uno elevado: CreateMutexW devuelve
    # un handle nulo y GetLastError() == ERROR_ACCESS_DENIED).
    ALREADY_RUNNING = "already_running"
    # No se pudo ni comprobar si habia otra instancia. Mejor no arrancar sin
    # garantia de unicidad que arriesgarse a correr dos instancias sin
    # saberlo (fallar cerrado).
    FAILED = "failed"


def _classify_mutex_result(handle: int | None, last_error: int) -> AcquireResult:
    """Logica pura de interpretar CreateMutexW, separada del FFI para poder probarla."""
    if handle:
        if last_error == _ERROR_ALREADY_EXISTS:
            return AcquireResult.ALREADY_RUNNING
        return AcquireResult.ACQUIRED
    if last_error == _ERROR_ACCESS_DENIED:
        return AcquireResult.ALREADY_RUNNING
    return AcquireResult.FAILED


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

    def acquire(self) -> AcquireResult:
        """ACQUIRED si somos la primera instancia; ver AcquireResult para los demas casos."""
        if sys.platform == "win32":
            # use_last_error=True guarda el codigo de error en un threadlocal
            # privado de ctypes que ctypes.get_last_error() lee sin hacer una
            # llamada FFI aparte. Con `ctypes.windll.kernel32` normal, entre
            # CreateMutexW y una llamada posterior a GetLastError() ctypes
            # puede ejecutar codigo (marshalling, el propio dispatch de la
            # llamada) que pise el codigo de error real antes de leerlo.
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
            last_error = ctypes.get_last_error()
            result = _classify_mutex_result(handle, last_error)
            if result is AcquireResult.ACQUIRED:
                self._handle = handle
            elif result is AcquireResult.FAILED:
                _log.error(
                    "No se pudo crear el mutex de instancia unica (codigo de error %s)",
                    last_error,
                )
            return result
        import fcntl

        self.config_dir.mkdir(parents=True, exist_ok=True)
        f = open(self.config_dir / "instance.lock", "w")  # noqa: SIM115
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return AcquireResult.ALREADY_RUNNING
        self._handle = f
        return AcquireResult.ACQUIRED

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


_MB_ICONWARNING = 0x30
_MB_OK = 0x0


def notify_user(message: str, title: str = "pr-watch") -> None:
    """Avisa al usuario de un fallo fuera del log.

    En un build --windowed (asi se empaqueta en Windows) stderr no va a
    ningun lado, asi que ahi hace falta un dialogo nativo de verdad. En otras
    plataformas no hay ese problema: basta con lo que ya exista (log/stderr).
    """
    if sys.platform == "win32":
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.MessageBoxW(None, message, title, _MB_ICONWARNING | _MB_OK)
        return
    _log.error("%s", message)
    print(message, file=sys.stderr)
