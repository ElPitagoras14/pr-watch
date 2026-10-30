"""Construye el ejecutable de la plataforma actual: `uv run build.py`.

Windows -> dist/pr-watch.exe (con icono y recurso de version).
Linux   -> dist/pr-watch.
PyInstaller no compila de forma cruzada: cada uno se construye en su sistema.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "pr_watch" / "ui"
NAME = "pr-watch"

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
        args += ["--hidden-import", "gi", "--collect-submodules", "gi.overrides"]

    print(f"Construyendo {NAME} {ver} para {sys.platform}…")
    try:
        PyInstaller.__main__.run(args)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = ROOT / "dist" / (f"{NAME}.exe" if sys.platform == "win32" else NAME)
    print(f"Listo: {out} ({out.stat().st_size / 1_000_000:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
