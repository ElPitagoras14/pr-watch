## 1. Verificar la base de construcción

- [x] 1.1 Comprobar en un contenedor `ubuntu:22.04` (local con Docker, sin workflow desechable). Debe instalar `libgirepository1.0-dev`, `libcairo2-dev`, `pkg-config`, `build-essential`, `git`, `ca-certificates`, `curl` y los `gir1.2-*`, fijar `PyGObject>=3.50,<3.51` y ejecutar `uv sync`. Verificación: PyGObject 3.50.x y pycairo compilan sin error.
- [x] 1.2 En la misma ejecución, correr `uv run build.py` y `ldd` sobre `_gi*.so` y sobre el binario. Verificación: anotar la glibc máxima referenciada (`objdump -T | grep GLIBC_`), que debe ser ≤ 2.35.
- [x] 1.3 Si 1.1 o 1.2 fallan, detenerse y plantearlo al usuario antes de seguir. Si pasan, fijar en `release.yml` la lista exacta de paquetes y borrar el workflow desechable.

## 2. Dependencias

- [x] 2.1 Cambiar en `pyproject.toml` a `"PyGObject>=3.50,<3.51; sys_platform == 'linux'"`, con un comentario sobre `girepository-1.0` y el piso de glibc, y regenerar `uv.lock`. Verificación: `uv lock --check` pasa y el bloqueo muestra pygobject 3.50.x.

## 3. Chequeo de plataforma

- [x] 3.1 Reescribir `pr_watch/platform_check.py` según D4: comprobar la glibc antes de `import gi` cuando corre empaquetado, conservar el texto del `ImportError`, no recomendar `python3-gi` en el binario y mantener el mensaje actual desde el código fuente. Registrar el error original en el log. Verificación: `ruff check` y `pyright` pasan.
- [x] 3.2 Añadir `tests/test_platform_check.py` con los cuatro escenarios de `specs/packaging/spec.md`, simulando `sys.frozen`, `os.confstr` e `import gi` con `unittest.mock`. Las pruebas deben correr también en Windows. Verificación: `uv run python -m unittest discover -s tests` pasa.
- [x] 3.3 Añadir `--check-system` a `pr_watch/__main__.py` (D5): ejecuta el chequeo y sale con 0 o 1 sin tomar la instancia única. Añadir la prueba correspondiente. Verificación: `uv run python -m pr_watch --check-system` sale con 0 en una máquina de desarrollo correcta.

## 4. Construcción

- [x] 4.1 En `build.py`, rama de Linux: generar el `.spec` con los mismos argumentos, filtrar de `a.binaries` y `a.datas` las bibliotecas de GLib y sus dependencias directas (D3) y construir desde ese `.spec`. Windows queda igual. Verificación: `pyi-archive_viewer` no lista GLib ni sus dependencias, y `--check-system` pasa en `ubuntu:22.04`, `debian:12`, `debian:13` y `ubuntu:24.04` con solo los paquetes de ejecución.

- [x] 4.2 Optimizar el tamaño: lista blanca de bibliotecas, sin iconos ni typelibs empaquetados y `--strip` (D3). Verificación: el binario pasa de 52,5 MB a 22,3 MB y arranca la aplicación entera 12 s en `ubuntu:22.04`, `debian:12`, `debian:13` y `ubuntu:24.04`.

## 5. Pipeline

- [x] 5.1 Pasar `build-linux` a `container: ubuntu:22.04` con los paquetes fijados en 1.3. Quitar `sudo` y actualizar el comentario sobre la glibc. Verificación: el job construye y sube el artefacto.
- [x] 5.2 Añadir el job `smoke-linux` con matriz `ubuntu:22.04` y `debian:13`: instalar solo los paquetes de ejecución del README más `xvfb`, descargar el artefacto y ejecutar `xvfb-run -a ./pr-watch-<v>-linux --check-system`. Hacer que `tag` dependa de él. Verificación: el job pasa en ambos contenedores, y si se fuerza un fallo (por ejemplo, sin `gir1.2-webkit2-4.1`) el pipeline se detiene antes de `tag`.
- [x] 5.3 Actualizar las notas del release en `release.yml`: construido en Ubuntu 22.04, glibc 2.35 o más nueva (Ubuntu 22.04+, Debian 12+, Mint 21+, Fedora 36+) y mención de `--check-system`. Verificación: el `notas.md` generado en la ejecución muestra el texto nuevo.

## 6. Documentación y cierre

- [x] 6.1 Actualizar `README.md`: sección de instalación en Linux con el piso nuevo, y sección de construcción (para construir en local en distribuciones con glib < 2.80 hace falta `libgirepository1.0-dev`, ya cubierto por el bloqueo). Verificación: lectura del diff.
- [x] 6.2 Subir la versión a `0.1.5` en `pyproject.toml` y `pr_watch/__init__.py`. Verificación: `tests/test_version.py` y `python scripts/release_version.py` pasan.
- [x] 6.3 Comprobación final: si es posible, ejecutar el binario publicado en una máquina Debian 12 real y verificar que arranca en la bandeja. **Pospuesta por decisión del usuario: solo es posible tras publicar la 0.1.5; se comprueba después del release.**
