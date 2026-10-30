## Why

Una persona con Debian 12 ejecutó `pr-watch-0.1.4-linux`. El binario le pidió `sudo apt install python3-gi`; lo instaló y el mensaje siguió apareciendo. Hay dos fallos detrás:

- El binario se construye en `ubuntu-24.04` con PyGObject 3.58.1 (exige `girepository-2.0` ≥ 2.80) y necesita glibc ≥ 2.38. Eso deja fuera distribuciones que siguen con soporte y son comunes en escritorio: Debian 12, Ubuntu 22.04 LTS, Linux Mint 21.
- `platform_check.py` atrapa el `ImportError` de `import gi` y recomienda `python3-gi`. En el binario empaquetado, ese paquete del sistema no se usa nunca: lo que falla es el `_gi.so` empaquetado al no encontrar `GLIBC_2.38`, y el error real se pierde.

## What Changes

- El binario de Linux se construye en una base con glibc 2.35 (contenedor `ubuntu:22.04`), y el piso de glibc baja de 2.38 a 2.35. Pasan a funcionar Debian 12, Ubuntu 22.04 y Mint 21, y siguen funcionando Debian 13, Ubuntu 24.04 y Fedora recientes.
- En Linux, PyGObject se fija a la serie 3.50, la última que usa `girepository-1.0`, que existe en todas esas distribuciones.
- El binario deja de llevar dentro GTK, GLib y el resto de la pila gráfica (también el tema de iconos y los typelibs): los toma del sistema. Así un glib empaquetado más antiguo no choca con el de una distribución más nueva, y el binario de Linux pasa de 52,5 MB a 22,3 MB.
- El pipeline prueba el arranque del binario en las distribuciones mínima y más reciente antes de publicar.
- El chequeo de arranque distingue el binario empaquetado del entorno de desarrollo. Dentro del binario no recomienda `python3-gi`: muestra el error real de importación y la glibc del sistema frente a la mínima que exige el binario.
- El README y las notas del release declaran el piso nuevo y dejan de sugerir "constrúyelo allí" sin decir qué versión de PyGObject hace falta.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

Las dos capacidades se definen en cambios que todavía no se han archivado (`add-pr-watch-tray-app` y `add-release-pipeline`). Por eso los deltas añaden requisitos nuevos en lugar de modificar los existentes.

- `packaging`: el diagnóstico de arranque en Linux debe distinguir el binario empaquetado y explicar una incompatibilidad de glibc, en lugar de recomendar un paquete que no se usa.
- `release-pipeline`: el binario de Linux debe construirse para un piso de glibc declarado (2.35) y probarse en las distribuciones de los extremos antes de publicarse.

## Impact

- `pr_watch/platform_check.py` y sus pruebas nuevas en `tests/`.
- `pyproject.toml` y `uv.lock`: restricción de PyGObject en Linux.
- `build.py`: exclusión de las bibliotecas de GLib del paquete de Linux.
- `.github/workflows/release.yml`: el job `build-linux` corre en el contenedor `ubuntu:22.04` con `libgirepository1.0-dev`; se añade la prueba de arranque y se cambia el texto de las notas.
- `README.md`: requisitos de Linux y sección de construcción.
- Compatibilidad: ninguna distribución que funcione hoy deja de funcionar, aunque esto hay que verificarlo en el pipeline (ver `design.md`). El tamaño del binario baja un poco al no llevar glib.
