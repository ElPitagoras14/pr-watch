## Why

Hoy los ejecutables se construyen a mano (`uv run build.py`) en cada plataforma y se publican a mano: el README dice "descarga `pr-watch.exe`", pero no hay ningún release en el repositorio ni un solo tag, así que ese enlace no existe. Además el binario de Linux solo se puede construir en Linux, de modo que publicar una versión obliga hoy a tener dos máquinas. Un pipeline en GitHub Actions resuelve las dos cosas: construye los dos binarios en sus respectivos runners y los publica en un release atado a un tag, a partir de la versión que ya vive en el repositorio.

## What Changes

- Se añade un workflow de GitHub Actions, `release`, que se dispara en cada push a `main` y encadena cuatro etapas: **check-version → build → tag → release**.
- **check-version** lee la versión del proyecto y decide si hay algo que publicar: si el tag `v<versión>` ya existe en el repositorio, el pipeline termina en verde sin construir ni publicar. Publicar una versión pasa a ser, simplemente, subir a `main` un commit que sube la versión.
- Antes de construir corre una **puerta de verificación** con las mismas órdenes que ya documenta el README: `unittest`, `ruff check` y `pyright`. Si falla, no se construye ni se publica nada.
- **build** produce los dos ejecutables en paralelo: `pr-watch.exe` en un runner de Windows y `pr-watch` en `ubuntu-24.04`, en ambos casos con la orden de construcción que ya existe (`uv run build.py`), sin duplicar su lógica en YAML.
- **tag** crea y empuja el tag anotado `v<versión>` sobre el commit construido, solo después de que los dos binarios existen.
- **release** publica un GitHub Release sobre ese tag con los dos binarios adjuntos y notas generadas a partir de los commits desde el tag anterior.
- El pipeline es **idempotente**: relanzarlo sobre un commit ya publicado no crea un tag duplicado ni un segundo release.
- Se documenta en el README cómo se publica una versión y qué distribuciones de Linux cubre el binario oficial.

## Capabilities

### New Capabilities

- `release-pipeline`: el workflow de integración y publicación en GitHub Actions — cuándo se dispara, qué comprueba antes de construir, en qué orden corren las etapas y qué garantías de idempotencia y permisos ofrece.
- `release-artifacts`: qué se publica — los dos ejecutables, con qué nombres se descargan, el tag que los ata a un commit y el contenido del release.

### Modified Capabilities

<!-- Ninguna. `packaging` sigue igual: el pipeline usa la orden de construcción existente, no cambia qué produce ni cómo. -->

## Impact

- **Nuevos archivos**: `.github/workflows/release.yml` y un pequeño script de apoyo para leer la versión y comparar contra los tags existentes, invocable también en local.
- **Código existente**: ninguno cambia de comportamiento. `build.py` se usa tal cual; la versión se sigue leyendo de `pyproject.toml` y `pr_watch/__init__.py`, que `tests/test_version.py` ya obliga a mantener en sincronía.
- **Entorno de construcción en Linux**: el runner necesita las bibliotecas de desarrollo de GTK/GObject para que `uv sync` compile PyGObject 3.58.1 (exige `girepository-2.0` ≥ 2.80, que es la razón de fijar `ubuntu-24.04` y no `ubuntu-22.04`). El binario resultante queda atado a la glibc de ese runner, lo que fija el piso de distribuciones soportadas.
- **Permisos**: el workflow necesita permiso de escritura sobre el contenido del repositorio (`contents: write`) para empujar el tag y crear el release; usa el `GITHUB_TOKEN` del propio workflow, sin secretos nuevos.
- **Documentación**: README gana una sección de publicación y una nota sobre el piso de glibc.
