"""Imprime la version del proyecto, o falla si no es unica y bien formada.

La version vive en dos sitios -- `pyproject.toml` y `pr_watch/__init__.py` --, y el
pipeline de publicacion la necesita antes de sincronizar dependencias. Por eso esto
solo usa la biblioteca estandar y lee el paquete como texto en lugar de importarlo:
en Linux, importar `pr_watch` arrastraria un `uv sync` que compila PyGObject.

    python scripts/release_version.py

En GitHub Actions escribe ademas `version=<valor>` en `$GITHUB_OUTPUT`.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "pr_watch" / "__init__.py"

# MAJOR.MINOR.PATCH, sin sufijos: el tag y el recurso de version del .exe son asi.
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
DUNDER = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


class VersionError(Exception):
    """La version no se puede determinar: el mensaje dice por que."""


def leer_pyproject(path: Path) -> str:
    datos = tomllib.loads(path.read_text("utf-8"))
    proyecto = datos.get("project")
    if not isinstance(proyecto, dict) or "version" not in proyecto:
        raise VersionError(f"{path.name} no declara project.version")
    version = proyecto["version"]
    if not isinstance(version, str):
        raise VersionError(f"{path.name} declara project.version que no es una cadena")
    return version


def leer_paquete(path: Path) -> str:
    # A proposito por texto y no por import: ver el docstring del modulo.
    encontrado = DUNDER.search(path.read_text("utf-8"))
    if encontrado is None:
        raise VersionError(f"{path.name} no declara __version__")
    return encontrado.group(1)


def version(root: Path = ROOT) -> str:
    pyproject = leer_pyproject(root / "pyproject.toml")
    paquete = leer_paquete(root / "pr_watch" / "__init__.py")
    if pyproject != paquete:
        raise VersionError(
            "la version diverge: pyproject.toml dice "
            f"{pyproject!r} y pr_watch/__init__.py dice {paquete!r}"
        )
    if not SEMVER.match(pyproject):
        raise VersionError(f"la version {pyproject!r} no tiene la forma MAJOR.MINOR.PATCH")
    return pyproject


def main(argv: list[str] | None = None) -> int:
    raiz = Path(argv[0]).resolve() if argv else ROOT
    try:
        ver = version(raiz)
    except (VersionError, OSError, tomllib.TOMLDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(ver)
    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"version={ver}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
