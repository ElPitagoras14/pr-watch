"""Comprobacion de las bibliotecas de sistema que el binario de Linux no lleva.

GTK 3, WebKit2GTK 4.1 y Ayatana AppIndicator se toman del sistema (D17). Si
falta alguna, mejor un mensaje que diga que paquete instalar que una traza.
"""

from __future__ import annotations

import logging
import os
import sys

_log = logging.getLogger(__name__)

# glibc mas antigua en la que corre el binario publicado. Es la del contenedor
# de construccion de `build-linux` en .github/workflows/release.yml; el job
# `smoke-linux` avisa si las dos dejan de coincidir.
MIN_GLIBC = (2, 35)

# (espacio de nombres GI, version, paquete de Debian/Ubuntu que lo proporciona)
REQUIRED: tuple[tuple[str, str, str], ...] = (
    ("Gtk", "3.0", "gir1.2-gtk-3.0"),
    ("WebKit2", "4.1", "gir1.2-webkit2-4.1"),
    ("AyatanaAppIndicator3", "0.1", "gir1.2-ayatanaappindicator3-0.1"),
)


def glibc_version() -> tuple[int, int] | None:
    """Version de la glibc del sistema, o None si no se puede saber (musl, Windows)."""
    try:
        raw: str = os.confstr("CS_GNU_LIBC_VERSION")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        return None
    name, _, version = raw.partition(" ")
    if name != "glibc":
        return None
    try:
        major, minor = version.split(".")[:2]
        return int(major), int(minor)
    except ValueError:
        return None


def _fmt(version: tuple[int, int]) -> str:
    return f"{version[0]}.{version[1]}"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _gi_failure(error: ImportError) -> str:
    """Mensaje cuando `import gi` falla.

    Dentro del binario, PyGObject va empaquetado: `python3-gi` del sistema no
    interviene, asi que recomendarlo despista. Lo habitual es una glibc mas
    antigua que la del sistema donde se construyo.
    """
    if not _frozen():
        return (
            "pr-watch necesita bibliotecas del sistema que faltan: PyGObject.\n"
            "En Debian/Ubuntu se instalan con:\n\n    sudo apt install python3-gi\n"
        )
    lines = [f"pr-watch no pudo cargar PyGObject, que lleva dentro: {error}"]
    system = glibc_version()
    if system is not None and system < MIN_GLIBC:
        lines.append(
            f"Este binario necesita glibc {_fmt(MIN_GLIBC)} o mas nueva "
            f"y este sistema tiene {_fmt(system)}. Actualiza la distribucion."
        )
    return "\n".join(lines) + "\n"


def missing_libraries() -> list[tuple[str, str, str]]:
    """Espacios de nombres GI que faltan; vacio si todo esta o no es Linux."""
    if not sys.platform.startswith("linux"):
        return []
    missing: list[tuple[str, str, str]] = []
    import gi  # type: ignore[import-not-found]

    for namespace, version, package in REQUIRED:
        try:
            gi.require_version(namespace, version)  # type: ignore[attr-defined]
            __import__(f"gi.repository.{namespace}")
        except (ValueError, ImportError):
            missing.append((namespace, version, package))
    return missing


def report(missing: list[tuple[str, str, str]]) -> str:
    names = ", ".join(f"{ns} {ver}".strip() for ns, ver, _ in missing)
    packages = " ".join(pkg for _, _, pkg in missing)
    _log.error("Faltan bibliotecas del sistema: %s", names)
    return (
        f"pr-watch necesita bibliotecas del sistema que faltan: {names}.\n"
        f"En Debian/Ubuntu se instalan con:\n\n    sudo apt install {packages}\n"
    )


def check() -> str | None:
    """Mensaje para el usuario si el arranque no puede seguir, o None si todo esta."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        missing = missing_libraries()
    except ImportError as e:
        _log.error("No se pudo importar gi: %s", e)
        return _gi_failure(e)
    return report(missing) if missing else None
