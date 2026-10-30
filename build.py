"""Construye el ejecutable de la plataforma actual: `uv run build.py`.

Windows -> dist/pr-watch.exe (con icono y recurso de version).
Linux   -> dist/pr-watch.
PyInstaller no compila de forma cruzada: cada uno se construye en su sistema.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "pr_watch" / "ui"
NAME = "pr-watch"

# Lo que PyInstaller arrastra por defecto y aqui no se usa. Pillow es el grueso:
# `icon.py` solo traza elipses y lineas y guarda .ico/.png, asi que los codecs y
# el motor de texto son 10,6 MB sin comprimir de peso muerto. Quitarlos es
# seguro: `Image.init()` se traga el ImportError de cada plugin e `ImageFont` ya
# contempla que `_imagingft` falte (DeferredError), que es justo lo que pasa al
# excluirlo.
UNUSED = (
    "PIL.AvifImagePlugin",  # 7,7 MB: el codec AVIF, el mas pesado con diferencia
    "PIL._avif",
    "PIL._imagingft",  # 2,2 MB: FreeType, y no se dibuja texto
    "PIL.WebPImagePlugin",
    "PIL._webp",
    "PIL.ImageCms",  # perfiles de color
    "PIL._imagingcms",
    "PIL.ImageTk",  # arrastra tkinter entero
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
)

# En Linux el binario lleva Python y sus extensiones, y nada mas: GTK, GLib, WebKit y
# toda la pila grafica se toman del sistema, que ya los tiene porque son requisito
# (D17 y D3 de fix-linux-glibc-floor). Los hooks de PyInstaller para PyGObject los
# recogen por defecto (libgtk, pango, cairo, glib... mas el tema de iconos Adwaita,
# 9 MB en 6.900 ficheros), y eso pesa y ademas mezcla dos versiones de GLib/GTK en el
# proceso: la de la distribucion de construccion (la mas antigua soportada) gana a la
# del sistema y revienta en las nuevas (libmount sin MOUNT_2_40 en Debian 13).
# Lo unico de nivel superior que se queda:
#   libpython      el interprete.
#   libgirepository-1.0   GTK no la carga, y Debian 13 / Ubuntu 24.04 ya solo traen
#                  girepository-2.0, asi que del sistema no la encontrarian.
#   libffi, libz, liblzma, libexpat   las que cargan los modulos de la biblioteca
#                  estandar; baratas y estables.
BUNDLED_LIBS = (
    "libpython",
    "libgirepository-1.0",
    "libffi",
    "libz.",
    "liblzma",
    "libexpat",
)

# Datos que traen los hooks de gi y vienen del sistema: el tema de iconos, los
# plugins de GIO y los typelibs (los gir1.2-* son requisito y ya los tienen).
SYSTEM_DATA = ("share/icons/", "gio_modules/", "gi_typelibs/")

# Se inserta en el .spec justo antes de crear el PYZ, cuando `a.binaries` ya esta calculado.
# Los binarios dentro de un paquete (pillow.libs/, cryptography/...) llevan "/" y no se tocan.
SPEC_FILTER = f"""_BUNDLED = {BUNDLED_LIBS!r}
_SYSTEM_DATA = {SYSTEM_DATA!r}
a.binaries = [
    b for b in a.binaries
    if not b[0].startswith(_SYSTEM_DATA)
    and not (b[0].startswith("lib") and "/" not in b[0] and not b[0].startswith(_BUNDLED))
]
a.datas = [d for d in a.datas if not d[0].startswith(_SYSTEM_DATA)]
"""

LAUNCHER = """\
import sys
from pr_watch.__main__ import main

sys.exit(main())
"""


def version() -> str:
    sys.path.insert(0, str(ROOT))
    from pr_watch import __version__

    return __version__


def version_file(path: Path, ver: str) -> Path:
    parts = [int(p) for p in ver.split(".")] + [0] * 4
    nums = tuple(parts[:4])
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040A04B0', [
      StringStruct('CompanyName', 'pr-watch'),
      StringStruct('FileDescription', 'pr-watch: pull requests de GitHub en la bandeja'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', '{NAME}'),
      StringStruct('OriginalFilename', '{NAME}.exe'),
      StringStruct('ProductName', 'pr-watch'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [0x040A, 1200])])
  ]
)
""",
        "utf-8",
    )
    return path


def build_with_system_libs(args: list[str], work: Path) -> None:
    """Construye generando antes el .spec para quitarle lo que el sistema ya trae.

    La linea de ordenes de PyInstaller no permite excluir binarios, asi que se
    genera el .spec con las mismas opciones, se le inserta el filtro y se
    construye desde el.
    """
    # Por importlib: los stubs de PyInstaller solo declaran `run`, y estas dos
    # funciones (las mismas que usa `run`) existen en la version fijada.
    pyi = importlib.import_module("PyInstaller.__main__")

    options = vars(pyi.generate_parser().parse_args(args))
    spec = Path(pyi.run_makespec(**options))
    text = spec.read_text("utf-8")
    marker = "pyz = PYZ("
    if marker not in text:
        raise SystemExit(f"El .spec generado no tiene '{marker}': PyInstaller cambio de formato")
    spec.write_text(text.replace(marker, SPEC_FILTER + marker, 1), "utf-8")
    pyi.run(
        [
            str(spec),
            "--noconfirm",
            "--clean",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(work / "build"),
        ]
    )


def main() -> int:
    import PyInstaller.__main__

    ver = version()
    work = Path(tempfile.mkdtemp(prefix="pr-watch-build-"))
    launcher = work / "pr_watch_launcher.py"
    launcher.write_text(LAUNCHER, "utf-8")

    args = [
        str(launcher),
        "--name",
        NAME,
        "--onefile",
        "--noconfirm",
        "--clean",
        "--paths",
        str(ROOT),
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(work / "build"),
        "--specpath",
        str(work),
        "--add-data",
        f"{UI}{os.pathsep}pr_watch/ui",
        # La vista previa no viaja en el ejecutable.
        "--exclude-module",
        "pr_watch.preview",
        *[arg for mod in UNUSED for arg in ("--exclude-module", mod)],
        "--collect-submodules",
        "pr_watch",
        "--collect-submodules",
        "desktop_notifier",
        "--collect-submodules",
        "keyring.backends",
    ]

    if sys.platform == "win32":
        args += ["--windowed", "--version-file", str(version_file(work / "version.txt", ver))]
        try:
            from pr_watch import icon

            ico = icon.write_ico(work / f"{NAME}.ico")
            args += ["--icon", str(ico)]
        except Exception as e:
            # Sin icono el ejecutable sigue siendo util; no poder construirlo, no.
            print(f"AVISO: no se pudo generar el icono ({e}); el .exe sale sin icono")
    else:
        # GTK, WebKit2GTK y AppIndicator se toman del sistema (D17): llevarlos
        # dentro haria el binario enorme y fragil entre distribuciones.
        # Los submodulos de gi.overrides se cargan dinamicamente, asi que el
        # analisis estatico no los ve; sin ellos falta GObject.idle_add y
        # pystray revienta al crear el icono.
        args += ["--hidden-import", "gi", "--collect-submodules", "gi.overrides", "--strip"]

    print(f"Construyendo {NAME} {ver} para {sys.platform}…")
    try:
        if sys.platform == "win32":
            PyInstaller.__main__.run(args)
        else:
            build_with_system_libs(args, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = ROOT / "dist" / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    print(f"Listo: {out} ({out.stat().st_size / 1_000_000:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
