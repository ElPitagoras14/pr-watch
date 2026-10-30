## 1. Base del proyecto y spike de plataforma

- [x] 1.1 Crear la estructura de D2, `pyproject.toml` con Python 3.13 y las versiones de D1 (desarrollo en `[dependency-groups] dev`), `.python-version`, configuración de `pyright` (strict) y `ruff` en `pyproject.toml`, `.editorconfig` y `pr_watch/__init__.py` con la versión `0.1.0`; verificar que `uv sync` genera `uv.lock` sin errores, que `uv run ruff check` y `uv run pyright` pasan, y que `uv run python -m unittest discover -s tests` corre (aunque haya cero pruebas)
- [ ] 1.2 Spike: `pystray` con un icono cualquiera y una ventana `pywebview` oculta que se muestra y oculta desde el menú y, en Windows, con clic izquierdo; verificar a mano en Windows y en Linux (WSLg con Ubuntu 22.04 sirve para la ventana; la bandeja requiere un escritorio con StatusNotifier) que no hay bloqueo y que `Salir` termina el proceso. Documentar el patrón de hilos que funcionó en un comentario de `app.py`
- [x] 1.3 `log.py`: log rotativo en el directorio de configuración; verificar con una prueba que un mensaje con un token falso pasado por el objeto de credencial no aparece en el archivo

## 2. Configuración y credencial

- [x] 2.1 `config.py`: valores por defecto, creación en el primer arranque, TOML ilegible (conserva el archivo), claves desconocidas, tabla `[github]` con `org`, suelo de 30 s, tope de 1 a 20, proveedor desconocido, escritura con `tomli-w`; verificar con pruebas que cubren cada escenario de `app-config`
- [x] 2.2 `credential.py`: orden de lectura `PR_WATCH_TOKEN` → `.env` → keyring → archivo; ignora `GITHUB_TOKEN`/`GH_TOKEN`; respaldo a archivo `0600` con aviso; borrado idempotente; el `repr` oculta el token; verificar con pruebas que usan un backend de keyring en memoria y uno `fail`
- [x] 2.3 `autostart.py`: activar, desactivar y consultar la clave `Run` en Windows y el `.desktop` en Linux, con la entrada del sistema como única fuente de verdad; apagado por defecto; al arrancar, si está activado y la ruta cambió, se actualiza; desde el código queda inhabilitado (`sys.frozen`); verificar con pruebas que usan una clave de registro de prueba en `HKCU\Software\pr-watch-test` y un directorio temporal

## 3. Modelo neutro y proveedor de GitHub

- [x] 3.1 `providers/base.py`: dataclasses del modelo, `Relation`, `ChecksState`, `PrState`, errores clasificados, `Protocol` del proveedor y registro en `providers/__init__.py`; verificar con `uv run pyright` sin errores
- [x] 3.2 `github.py`, punto de envío: sesión `requests` con `truststore`, cabecera `Authorization`, timeout y rechazo de `mutation`/`subscription` antes de enviar; verificar con pruebas que un documento con `mutation` lanza el error sin llamar al transporte simulado
- [x] 3.3 `github.py`, `verify`: login y acceso a la organización; clasificar 401, organización inaccesible, límite agotado y fallo de red; verificar con pruebas sobre respuestas grabadas en `tests/fixtures/github/`
- [x] 3.4 `github.py`, `fetch_open`: la consulta con tres alias, paginación por alias, deduplicación por prioridad de relación, `complete=False` si falla una búsqueda; verificar con fixtures que incluyen un PR en dos relaciones y una relación con dos páginas
- [x] 3.5 `github.py`, traducción (D5): aprobaciones vigentes, aprobación superada por cambios pedidos, checks, `mergeable UNKNOWN` conserva el valor anterior, listo para fusionar, "te toca"; y `fetch_states` (fusionado, cerrado, inaccesible) y `block_url`; verificar con pruebas por regla
- [ ] 3.6 Comprobación con un token real de la organización: correr `python -m pr_watch.providers.github --check` (un modo de diagnóstico que imprime el resumen sin el token) y confirmar que checks, revisiones e hilos llegan con los permisos listados. Ajustar la lista de permisos de la ventana de ajustes si falta alguno

## 4. Sondeo, estado y novedades

- [x] 4.1 `state_store.py`: JSON por proveedor con versión de esquema, escritura atómica y descarte si está corrupto; verificar con pruebas (archivo corrupto, versión distinta, interrupción simulada entre escribir el temporal y `replace`)
- [x] 4.2 `polling.py`: diferencia entre el estado anterior y el resultado nuevo → novedades según `pr-polling`, línea base sin novedades, borradores ocultos, borrador que deja de serlo, caducidad de terminales (también tras reinicio), purga solo con `complete=True`, salida de relación sin novedad; verificar con una prueba por escenario de `pr-polling`
- [x] 4.3 Bucle de sondeo (en `poller.py`, para probarlo sin pywebview): primer sondeo inmediato, intervalo, "actualizar ahora" sin concurrencia, suspensión hasta `reset_at`, conservación de los últimos datos ante fallo; verificar con pruebas que usan un proveedor falso y un reloj inyectado

## 5. Modelo de vista e interfaz del panel

- [x] 5.1 `view.py`: secciones `CUENTA`/`MÍOS`/`POR REVISAR`, tope por bloque con el total real, prioridad de filas, etiqueta y color según el orden de `main-window`, segunda línea por bloque, quién aprobó, marcas de novedad, avisos (sin configurar, credencial inválida, desactualizado, suspendido), "hace X" del pie y texto del tooltip; verificar con pruebas por escenario de `main-window` y `unseen-counter` (tooltip)
- [x] 5.2 `ui/panel.html` + `panel.css` + `icons.css`: la estética de D8 en claro y oscuro, filas de dos líneas con truncado, iconos Segoe con respaldo SVG y el pin resaltado al fijar; verificar visualmente contra `panel-v2.html` del brainstorming usando la vista previa (tarea 5.4)
- [x] 5.3 `ui/panel.js`: `render(vm)`, acciones hacia `js_api`, Escape oculta, `blur` avisa, mide su alto tras cada render, refresca "hace X" cada 10 s, `js_api` falso si no hay `window.pywebview`; verificar en la vista previa que cada acción registra su llamada en la consola
- [x] 5.4 `preview.py` + `ui/preview/index.html`: escenarios generados desde `view.py` (sin configurar, vacío, por encima del tope, todos los estados, novedades, desactualizado, límite agotado), selector de escenario y alternancia de tema; verificar que `python -m pr_watch.preview` abre el navegador y cada escenario se dibuja

## 6. Ventanas, bandeja e icono

- [x] 6.1 `icon.py` + `theme.py`: glifo de PR monocromo por código, claro u oscuro según la barra de tareas, punto de novedades; verificar con pruebas que a 16 px el glifo tiene píxeles opacos en las zonas de los tres nodos, que con y sin punto las imágenes difieren, y que no se regenera si la tupla no cambia
- [ ] 6.2 `tray.py`: icono, menú (`Abrir pr-watch`, `Actualizar ahora`, `Arrancar con la sesión` marcable e inhabilitado desde el código, `Salir`), clic izquierdo como alternancia en Windows, actualización de imagen y tooltip; verificar a mano en Windows
- [ ] 6.3 `windows.py` (panel): ventana sin marco, siempre encima y oculta al arrancar; `js_api` de D7 con la lista blanca de URLs; mostrar/ocultar; ocultar al perder el foco salvo fijado o ajustes abiertos; fijado que no se hereda; empujar `render` en cada cambio; verificar con pruebas de la lógica de ocultado (sin ventana real) y a mano el comportamiento
- [x] 6.4 `placement.py`: `Shell_NotifyIconGetRect` con respaldo al área de trabajo, límites de pantalla y DPI; verificar con pruebas de la geometría (icono en cada borde, pantalla secundaria) y a mano con la barra de tareas abajo y a un lado
- [x] 6.5 Contador de novedades en `app.py`: suma por novedad, cero al abrir el panel, marcas limpias al cerrarlo, novedad con el panel visible no suma, no persiste; verificar con pruebas por escenario de `unseen-counter`

## 7. Ventana de ajustes

- [x] 7.1 `ui/settings.html` + `settings.js`: misma estética, cabecera arrastrable, organización rellena, token enmascarado y vacío, Ctrl+V, permisos y enlace para crear el token, intervalo, tope, notificaciones, abrir `config.toml`, guardar/cancelar y cerrar sesión solo si `has_token`; verificar en la vista previa
- [ ] 7.2 Lógica de ajustes en `windows.py`/`app.py`: verificación en un hilo sin congelar, mensajes distintos para token inválido, organización inaccesible y red; editar tras verificar invalida; guardar sin token conserva el guardado; guardar aplica en caliente (intervalo, tope que redibuja, credencial nueva que arranca el sondeo); cancelar no escribe; error de disco avisado; cerrar sesión deja la ventana abierta; ventana única; cerrar el panel cierra los ajustes; primera apertura sin token muestra los ajustes una sola vez por sesión; verificar con pruebas de la lógica y a mano el flujo completo con un token real

## 8. Notificaciones e instancia única

- [x] 8.1 `notify.py`: hechos notificables (listo para fusionar, roto, cambios pedidos, nuevo a revisar), deduplicación persistida, nueva notificación tras revertirse, agrupación con más de tres, apagado por defecto, fallo registrado una sola vez; verificar con pruebas que usan un emisor falso
- [ ] 8.2 Emisión real con `desktop-notifier` y callback (abrir URL o panel); verificar a mano en Windows con un PR de prueba
- [x] 8.3 `single_instance.py`: mutex/lock y canal `show`; verificar a mano que arrancar dos veces deja un solo icono y muestra el panel de la primera

## 9. Empaquetado y cierre

- [ ] 9.1 `build.py` en Windows (`uv run build.py`): genera el `.ico` desde `icon.py`, ejecuta PyInstaller `--onefile --windowed` con `pr_watch/ui` como datos y el recurso de versión, y avisa sin fallar si no puede generar el icono; verificar que `python build.py` produce `dist/pr-watch.exe`, que arranca en un Windows sin Python y que el Explorador muestra la marca
- [ ] 9.2 `build.py` en Linux: PyInstaller `--onefile` con `PyGObject` y `pr_watch/ui`, excluyendo GTK/WebKit/AppIndicator, más la comprobación de bibliotecas al arrancar con el mensaje del paquete que falta; verificar construyendo en WSL Ubuntu 22.04 que `dist/pr-watch` arranca en la bandeja de un escritorio Linux sin `uv` ni venv, y que, sin WebKit2GTK, termina nombrando `gir1.2-webkit2-4.1`. Si no hay escritorio Linux disponible, dejar anotado en `VERIFICACION.md` qué partes quedaron sin verificar
- [x] 9.3 `README.md` en español, al estilo del de mr-watch: qué vigila, qué no hace, el token y sus permisos, configuración, descarga y requisitos de cada ejecutable (bibliotecas del sistema en Linux), cómo construir en cada plataforma, vista previa para desarrollo; y `.gitignore` con `.env`, `dist/`, `build/` y `.superpowers/`; verificar leyendo el README contra las especificaciones
- [ ] 9.4 Verificación de punta a punta con el `.exe`: primer arranque sin configurar (sin ventanas, tooltip), primera apertura con ajustes, verificar y guardar, sondeo, punto de novedades al aprobar un PR de prueba, cero al abrir, fijar, Escape, perder el foco, `Salir` y rearranque sin novedades repetidas; anotar el resultado en `openspec/changes/add-pr-watch-tray-app/VERIFICACION.md`, como en mr-watch

## 10. Organización elegida de una lista

- [x] 10.1 `providers/base.py` y `github.py`: `list_scopes(token)` con `viewer { login organizations }`, ordenada y paginada, lista vacía sin error, 401 como credencial inválida; verificar con fixtures
- [x] 10.2 `app.py`/`windows.py`: `settings_verify_token(token)` (token escrito o el guardado) que devuelve login y organizaciones sin exponer el token; `settings_verify` pasa a comprobar la organización elegida; verificar con pruebas de la lógica
- [x] 10.3 `settings.html`/`settings.js`: token primero con `Verificar token`; selector de organización inhabilitado hasta verificar, con opción de escribirla a mano; elegir comprueba el acceso; con credencial guardada se verifica sola al abrir y preselecciona la configurada; cambiar el token inhabilita selector y guardado; verificar en la vista previa con escenarios de token con organizaciones, sin organizaciones y rechazado
- [x] 10.4 `github.py`: si la lista de organizaciones llega vacía (siempre con fine-grained), deducirlas de los dueños de tipo organización de `GET /user/repos` (hasta 5 páginas), sin permisos nuevos; verificar con fixtures (deducción, paginación, sin repositorios, y que con organizaciones no se consultan repositorios)
- [x] 10.5 Cuenta personal como ámbito: `user:<login>` en el selector (primero), `[github] user` en `config.toml`, búsquedas y enlaces con `user:`, verificación de que es la cuenta del token y ve repositorios suyos, etiqueta `Cuenta personal` (sin repetir el login, que ya sale en Usuario) en el panel y en Ajustes; verificar con pruebas y en la vista previa
