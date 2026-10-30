"""Comprobacion de las bibliotecas de sistema que el binario de Linux no lleva.

GTK 3, WebKit2GTK 4.1 y Ayatana AppIndicator se toman del sistema (D17). Si
falta alguna, mejor un mensaje que diga que paquete instalar que una traza.
"""

from __future__ import annotations

import logging
import sys

_log = logging.getLogger(__name__)

# (espacio de nombres GI, version, paquete de Debian/Ubuntu que lo proporciona)
REQUIRED: tuple[tuple[str, str, str], ...] = (
    ("Gtk", "3.0", "gir1.2-gtk-3.0"),
    ("WebKit2", "4.1", "gir1.2-webkit2-4.1"),
    ("AyatanaAppIndicator3", "0.1", "gir1.2-ayatanaappindicator3-0.1"),
)


def missing_libraries() -> list[tuple[str, str, str]]:
    if not sys.platform.startswith("linux"):
        return []
    try:
        import gi  # type: ignore[import-not-found]
    except ImportError:
        return [("PyGObject", "", "python3-gi")]
    missing: list[tuple[str, str, str]] = []
    for namespace, version, package in REQUIRED:
        try:
            gi.require_version(namespace, version)  # type: ignore[attr-defined]
            __import__(f"gi.repository.{namespace}")
        except (ValueError, ImportError):
            missing.append((namespace, version, package))
    return missing


def report(missing: list[tuple[str, str, str]]) -> None:
    names = ", ".join(f"{ns} {ver}".strip() for ns, ver, _ in missing)
    packages = " ".join(pkg for _, _, pkg in missing)
    message = (
        f"pr-watch necesita bibliotecas del sistema que faltan: {names}.\n"
        f"En Debian/Ubuntu se instalan con:\n\n    sudo apt install {packages}\n"
    )
    _log.error("Faltan bibliotecas del sistema: %s", names)
    print(message, file=sys.stderr)
