## Context

Estado actual (ver `proposal.md` para el motivo):

- `build-linux` corre directamente en `ubuntu-24.04` (glibc 2.39, glib 2.80). Instala `libgirepository-2.0-dev` y compila PyGObject 3.58.1 y pycairo desde sdist.
- `build.py` pasa `--hidden-import gi --collect-submodules gi.overrides` a PyInstaller. Por el análisis de dependencias binarias de `_gi.so`, el binario arrastra `libgirepository-2.0`, `libglib-2.0`, `libgobject-2.0`, `libgio-2.0` y `libgmodule-2.0`. GTK, WebKit y AppIndicator se toman del sistema (D17 de `add-pr-watch-tray-app`).
- `platform_check.missing_libraries()` hace `import gi`. Si falla, devuelve `("PyGObject", "", "python3-gi")`; `report()` imprime `sudo apt install python3-gi` y descarta la excepción.
- PyGObject pasó a `girepository-2.0` (glib ≥ 2.80) en 3.52. La serie 3.50 es la última que compila contra `girepository-1.0`, que está en Ubuntu 22.04 (1.72), Debian 12 (1.74), Debian 13 y Ubuntu 24.04.

## Goals / Non-Goals

**Goals:**
- Piso de glibc 2.35 para el binario publicado, sin perder ninguna distribución que funcione hoy.
- Un fallo de carga de `gi` en el binario debe explicarse con su causa real.
- Que el pipeline detecte una regresión de compatibilidad antes de publicar.

**Non-Goals:**
- Soportar RHEL/Alma/Rocky 9 (glibc 2.34) o distribuciones más antiguas. Exigiría construir sobre una base de 2021 y no tenemos usuarios ahí.
- Formatos AppImage, Flatpak o `.deb`.
- Cambiar la política de D17 (GTK y WebKit del sistema).

## Decisions

### D1. Construir dentro del contenedor `ubuntu:22.04`, no en el runner `ubuntu-22.04`

El job `build-linux` sigue en `runs-on: ubuntu-24.04`, pero declara `container: ubuntu:22.04`. La glibc del binario la determina la imagen del contenedor, que es fija y no depende del calendario de retirada de runners de GitHub. El runner `ubuntu-22.04` se retirará antes que la imagen de Docker.

Alternativas descartadas:
- `debian:12`: tiene glibc 2.36 y dejaría fuera Ubuntu 22.04 y Mint 21, que son las distribuciones más comunes del grupo.
- `manylinux_2_28` o similares: tienen glibc más baja, pero no traen GTK/WebKit 4.1 empaquetados para las pruebas ni para compilar contra `gir1.2-*`.

Consecuencias: el contenedor arranca como root sin `sudo` y sin `git`. El paso de dependencias instala también `git`, `ca-certificates` y `curl` (para `actions/checkout` y `setup-uv`) y `build-essential` (para compilar PyGObject y pycairo). El Python sigue siendo el de `uv` (python-build-standalone), que corre en glibc 2.17+, así que no limita el piso.

### D2. PyGObject `>=3.50,<3.51` solo en Linux

En `pyproject.toml`: `"PyGObject>=3.50,<3.51; sys_platform == 'linux'"`. Se regenera `uv.lock`. Se fija la serie y no un parche exacto, para recoger arreglos de la 3.50.x al actualizar el bloqueo. El bloqueo fija la versión real, igual que con el resto de dependencias.

Alternativa descartada: mantener 3.58 y empaquetar `libgirepository-2.0` compilado aparte. Habría que mantener una compilación de glib fuera de la distribución.

### D3. En Linux el binario solo lleva Python; GTK, GLib y la pila gráfica vienen del sistema

Los hooks de PyInstaller para PyGObject recogen por defecto la pila gráfica entera: `libgtk-3`, `libpango`, `libcairo`, GLib y sus dependencias, el tema de iconos Adwaita (9 MB en 6.900 ficheros) y los typelibs. Eso pesa y, además, mezcla dos versiones de GLib/GTK en el mismo proceso: la de la distribución de construcción, que es la más antigua soportada, gana a la del sistema y falla en las nuevas. Todo eso ya es requisito del usuario (`gir1.2-gtk-3.0` y compañía lo traen como dependencia), así que viaja del sistema.

`build.py` aplica una **lista blanca**: de las bibliotecas de nivel superior solo se quedan `libpython`, `libgirepository-1.0`, `libffi`, `libz`, `liblzma` y `libexpat`. Los binarios dentro de paquetes (`pillow.libs/`, `cryptography/`…) no se tocan. De los datos se quitan `share/icons/`, `gio_modules/` y `gi_typelibs/`. Además se pasa `--strip`.

Resultado medido (contenedor `ubuntu:22.04`): **52,5 MB → 22,3 MB** (−58 %); la glibc máxima de lo empaquetado baja de 2,35 a 2,34.

Hallazgos al implementar, comprobados ejecutando el binario en contenedores limpios:

- `libgirepository-1.0` **no** puede filtrarse: Debian 13 y Ubuntu 24.04 ya solo traen `girepository-2.0` (fallo real: `cannot open shared object file`).
- Filtrar solo GLib no bastaba: el `libmount.so.1` empaquetado (de 22.04) carecía de `MOUNT_2_40`, que exige el `libgio` 2.84 de Debian 13. La lista blanca lo resuelve de raíz.
- El binario **sin filtro** arrancaba con `--check-system` pero **moría al lanzar la aplicación en Debian 13** (`exit=1`); el filtrado lo arregla.
- Las pruebas de arranque completo (12 s bajo `xvfb` y `dbus`) dejan un `WebKitJavascriptError: SyntaxError: Unexpected EOF` en `panel.html`. Se reproduce idéntico en el binario sin filtro, así que es previo a este cambio y queda fuera de su alcance.

Implementación: la CLI de PyInstaller no permite excluir binarios, así que `build.py` genera el `.spec` con las mismas opciones (`generate_parser` + `run_makespec`, las funciones que usa `run`), inserta el filtro antes de `pyz = PYZ(` y construye desde ese `.spec`. La rama de Windows no cambia.

Alternativa descartada: lista negra de GLib y sus dependencias directas (la primera versión). Funcionaba, pero obligaba a ir añadiendo bibliotecas a medida que fallaban en cada distribución, y dejaba 14 MB de pila gráfica dentro.

### D4. Chequeo distinguiendo binario y fuente, con glibc explícita

`platform_check` cambia así:
- `missing_libraries()` conserva la excepción de `import gi` y deja de devolver solo el nombre del paquete. Devuelve un resultado que distingue "no carga gi" (con el texto de la excepción) de "falta el namespace X".
- Si `getattr(sys, "frozen", False)` es verdadero, el mensaje no menciona `python3-gi`. Lee `os.confstr("CS_GNU_LIBC_VERSION")` y, si es menor que `MIN_GLIBC = (2, 35)`, dice "este binario necesita glibc 2.35 o más nueva; este sistema tiene 2.XX". En todos los casos incluye la línea del `ImportError`.
- Desde el código fuente se mantiene el mensaje actual (`python3-gi`).
- La glibc solo se consulta cuando `import gi` falla: así el mensaje puede incluir el error real, y una glibc antigua que aun así funciona no bloquea el arranque.

`MIN_GLIBC` es una constante en `platform_check.py`, con un comentario que apunta al `container:` del workflow. La prueba de arranque de D5 en la distribución mínima es la que detecta si las dos se desincronizan.

### D5. Prueba de arranque con una opción `--check-system`

`__main__` acepta `--check-system`: ejecuta el chequeo de plataforma, imprime el resultado y sale con 0 o 1, sin tomar el bloqueo de instancia única ni abrir la bandeja. Es útil también como diagnóstico para usuarios.

Un job nuevo, `smoke-linux`, va después de `build-linux` y antes de `tag`. Usa una matriz de contenedores: `ubuntu:22.04` (el piso de glibc), `debian:12` (con la que falló la 0.1.4) y `debian:13` (la más reciente con glib ≥ 2.80, donde `girepository-1.0` ya no existe). En cada uno instala solo los paquetes de ejecución que pide el README, descarga el artefacto y ejecuta `xvfb-run -a ./pr-watch-<v>-linux --check-system`. `tag` pasa a depender de `smoke-linux`.

Alternativa descartada: probar dentro del mismo contenedor de construcción. Ahí están las cabeceras `-dev` y no se representa el sistema de un usuario.

## Risks / Trade-offs

- [PyGObject 3.50 no compila en `ubuntu:22.04`, por ejemplo porque meson exige algo más nuevo] → La primera tarea es un workflow desechable que lo comprueba antes de tocar nada más, igual que en `add-release-pipeline`. Si falla, se detiene el trabajo y se replantea con el usuario.
- [Alguna API usada por pywebview o pystray requiere PyGObject > 3.50] → Las pruebas bajo `xvfb` en el contenedor y `--check-system` lo cubren. pywebview 6.2.1 y pystray 0.19.5 no fijan mínimo de PyGObject.
- [Filtrar glib en `.spec` añade una pieza de construcción propia] → El filtro es una lista de prefijos documentada en `build.py`; la prueba en `debian:13` detecta si falta algo.
- [Una distribución sin `libgirepository-1.0` instalada] → Se instala como dependencia de `gir1.2-gtk-3.0` en Debian y Ubuntu. Si no carga, el mensaje de D4 lo dirá con el error real.
- [`MIN_GLIBC` desincronizado del contenedor] → Lo detecta `smoke-linux` en `ubuntu:22.04`.

## Migration Plan

No hay datos ni configuración que migrar. El siguiente release (`0.1.5`) publica el binario nuevo. Para revertir basta con volver a la versión anterior del workflow, `pyproject.toml` y `uv.lock`; los binarios ya publicados no cambian.
