## 1. Verificar el entorno de construcción de Linux

- [x] 1.1 Escribir un workflow desechable, disparable a mano, que en `ubuntu-24.04` instale las cabeceras de GObject-Introspection y Cairo, ejecute `uv sync` y muestre qué paquete `-dev` satisface a PyGObject 3.58.1 (`libgirepository-2.0-dev` o `libgirepository1.0-dev`)
- [x] 1.2 En la misma ejecución, correr `uv run build.py` y comprobar que sale `dist/pr-watch`, anotando el tamaño y la salida de `ldd` sobre el binario para conocer el piso de glibc real
- [x] 1.3 Si PyGObject no compila en `ubuntu-24.04`, detenerse y plantear al usuario la escalera de alternativas del diseño antes de seguir; si compila, fijar en el workflow definitivo la lista exacta de paquetes `apt` que funcionó y borrar el workflow desechable

## 2. Script de versión

- [x] 2.1 Crear `scripts/release_version.py`, solo con biblioteca estándar: lee la versión de `pyproject.toml` con `tomllib` y la de `pr_watch/__init__.py` por expresión regular, sin importar el paquete
- [x] 2.2 Validar que las dos coincidan y que tengan forma `MAJOR.MINOR.PATCH`; al fallar, salir con código distinto de cero y un mensaje que nombre los valores en conflicto o el valor mal formado
- [x] 2.3 Imprimir la versión por salida estándar y, cuando exista la variable de entorno de salidas de GitHub Actions, escribir también ahí la versión
- [x] 2.4 Añadir pruebas en `tests/` que cubran los tres casos: versiones coincidentes, versiones divergentes y versión mal formada, invocando el script como subproceso sobre archivos de prueba
- [x] 2.5 Comprobar que `ruff check` y `pyright` siguen pasando con el script y sus pruebas incluidos (`pyproject.toml` ya limita `pyright` a `pr_watch`, `tests` y `build.py`: añadir `scripts` a esa lista)

## 3. Jobs de verificación y de versión

- [x] 3.1 Crear `.github/workflows/release.yml` con disparo en push a `main`, permisos de solo lectura por defecto y un grupo de concurrencia que serialice las ejecuciones sin cancelarlas
- [x] 3.2 Implementar el job `check-version`: hacer checkout, ejecutar el script con el `python3` del runner y exponer la versión como salida
- [x] 3.3 En el mismo job, consultar `git ls-remote --tags origin` y exponer una salida booleana que diga si hay que publicar, falsa cuando el tag `v<versión>` ya existe
- [x] 3.4 Implementar el job `verify` en `windows-latest`, condicionado a esa salida: instalar `uv`, sincronizar dependencias y correr las tres órdenes del README (`unittest`, `ruff check`, `pyright`)

## 4. Jobs de construcción

- [x] 4.1 Implementar `build-windows` en `windows-latest`, dependiente de `verify`: sincronizar, `uv run build.py`, comprobar que existe `dist/pr-watch.exe`, renombrarlo a `pr-watch-<versión>-windows.exe` y subirlo como artefacto de la ejecución
- [x] 4.2 Implementar `build-linux` en `ubuntu-24.04`, dependiente de `verify`: instalar los paquetes `apt` confirmados en la tarea 1, sincronizar, correr las pruebas, `uv run build.py`, comprobar que existe `dist/pr-watch`, renombrarlo a `pr-watch-<versión>-linux` y subirlo como artefacto
- [x] 4.3 Comprobar en una ejecución real que los dos jobs corren en paralelo y que los dos artefactos quedan disponibles para los jobs siguientes

## 5. Etiquetado y publicación

- [x] 5.1 Implementar el job `tag`, dependiente de los dos jobs de construcción y con permiso de escritura sobre el contenido: configurar la identidad del bot de Actions, crear el tag anotado `v<versión>` sobre el commit de la ejecución y empujarlo sin forzar
- [x] 5.2 Implementar el job `release`, dependiente de `tag`: descargar los dos artefactos y crear el release con `gh release create` sobre el tag, titulado con la versión y con los dos binarios adjuntos con los nombres `pr-watch-<versión>-windows.exe` y `pr-watch-<versión>-linux`
- [x] 5.3 Generar las notas desde el historial y anteponer el cuerpo fijo que indica la distribución de construcción del binario de Linux y los paquetes del sistema que necesita; confirmar cómo combina `gh` ambas partes y, si no las concatena, armar el cuerpo completo y pasarlo como archivo de notas

## 6. Verificación de extremo a extremo

- [ ] 6.1 Comprobar el camino de no publicación: un push a `main` que no cambia la versión termina en verde tras `check-version`, sin construir ni etiquetar
- [x] 6.2 Comprobar el camino de publicación con la versión `0.1.0`: el pipeline construye, etiqueta `v0.1.0` y publica el release con los dos binarios
- [x] 6.3 Comprobar la idempotencia: relanzar la ejecución ya publicada termina en verde sin tocar el tag ni crear un segundo release
- [ ] 6.4 Descargar `pr-watch-<versión>-windows.exe` del release y comprobar que sus propiedades declaran la versión publicada y que arranca en la bandeja
  - Sobre el `.exe` descargado de `v0.1.1`: `FileVersion` y `ProductVersion` dicen `0.1.1`, y al ejecutarlo arranca y registra `pr-watch 0.1.1 arrancando`. No se llegó a ver el icono porque el usuario ya tenía una instancia en marcha y el ejecutable hizo lo correcto: pedirle que mostrara su panel y salir. Esa última comprobación es del escritorio del usuario.
- [x] 6.5 Descargar `pr-watch-<versión>-linux` del release, darle permiso de ejecución en un Linux con las bibliotecas documentadas y comprobar que arranca en la bandeja
  - Verificado sobre el binario descargado de `v0.1.1` en `ubuntu:24.04` con las bibliotecas documentadas, `xvfb` y bus de sesión: arranca, registra `pr-watch 0.1.1 arrancando`, crea el icono y sigue vivo al expirar el plazo de la prueba.
  - El binario de `v0.1.0` **no arrancaba**, por un defecto de `build.py` anterior a este cambio: no llevaba los submódulos de `gi.overrides`, que se cargan dinámicamente y el análisis estático de PyInstaller no ve, así que `GObject.idle_add` no existía y `pystray` fallaba al crear el icono. Con el arreglo (`--collect-submodules gi.overrides`), el binario arranca, crea el icono y sigue vivo. Verificado en `ubuntu:24.04` con las bibliotecas documentadas, `xvfb` y bus de sesión.
  - Queda abierto, **ajeno a este cambio**: en Linux el panel repite `WebKitJavascriptError: SyntaxError: Unexpected EOF`. No es empaquetado —los archivos de `pr_watch/ui` dentro del binario son idénticos a los de la fuente— y la aplicación sigue funcionando. Merece un change propio.

## 7. Documentación

- [x] 7.1 Añadir al README una sección de publicación: subir la versión en los dos sitios, fusionar a `main`, y qué hace el pipeline a partir de ahí
- [x] 7.2 Documentar el piso de distribuciones del binario oficial de Linux y cómo recuperarse si el pipeline deja un tag sin release
- [x] 7.3 Actualizar los enlaces de descarga de la sección de instalación para que apunten al último release
