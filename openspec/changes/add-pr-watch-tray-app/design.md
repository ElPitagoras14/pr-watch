## Context

Repositorio vacío. La referencia de comportamiento es mr-watch (`mr-watch`, Rust + egui), cuyas especificaciones se han portado casi una a una; las diferencias están en `proposal.md`. La referencia de stack y estética es usage-monitor-for-claude (Python + pystray + pywebview, con el popup en HTML/CSS/JS y empaquetado con PyInstaller). El motivo del cambio de stack es poder iterar rápido sobre la interfaz (ver `proposal.md`, *Why*).

Restricciones:
- Windows 10/11 y Linux con escritorio freedesktop. En las dos plataformas se entrega un ejecutable único de PyInstaller (ver `specs/packaging`).
- Solo github.com, una organización y un token. GitLab llegará después como otro proveedor.
- Interfaz en español.

## Goals / Non-Goals

**Goals:**
- Toda la lógica que decide (diferencias entre sondeos, novedades, prioridad de filas, etiquetas y colores, tooltip) en Python puro, probable con `unittest`, sin red ni interfaz.
- Interfaz "tonta": el JS solo dibuja un modelo de vista ya decidido y reenvía acciones al proceso.
- Un único conjunto de archivos de interfaz, compartido por la aplicación y la vista previa.
- Añadir un proveedor = un módulo nuevo más una entrada en el registro de proveedores.

**Non-Goals:**
- GitHub Enterprise Server, varias organizaciones o varias cuentas.
- Implementar el proveedor de GitLab (solo se deja el hueco).
- Acciones de escritura, diff o código.
- Instalador, paquetes `.deb`/AppImage/Flatpak, publicación en WinGet, firma de código o un pipeline de publicación. Quedan para un cambio posterior, como el `add-pipeline-release` de mr-watch.
- Traducciones.

## Decisions

### D1. Stack y versiones
**Python 3.13** fijo (`requires-python = ">=3.13,<3.14"`, `.python-version` = `3.13`), y para todo lo demás la versión más reciente compatible con 3.13 a fecha de este cambio:

| Paquete | Versión | Uso |
|---|---|---|
| `pywebview` | 6.2.1 | panel y ajustes |
| `pystray` | 0.19.5 | bandeja (última publicada) |
| `Pillow` | 13.0.0 | glifo, punto e `.ico` |
| `requests` | 2.34.2 | HTTP |
| `truststore` | 0.10.5 | CA del sistema |
| `keyring` | 25.7.0 | credencial |
| `tomli-w` | 1.2.0 | escritura de TOML (la lectura es `tomllib`) |
| `desktop-notifier` | 6.2.0 | notificaciones |
| `pyinstaller` (dev) | 6.22.3 | `.exe` |
| `pyright` (dev) | 1.1.414 | tipos, en modo `strict` |
| `ruff` (dev) | 0.17.3 | lint y formato |

**Gestión con `uv`** (0.10) en lugar de `pip` + `requirements.txt`: `pyproject.toml` declara las dependencias (las de desarrollo en `[dependency-groups] dev`) y `uv.lock` fija el árbol completo, con hashes. `uv sync` prepara el entorno y `uv run` ejecuta pruebas, vista previa y `build.py`. Se aprovecha lo moderno de 3.13: sintaxis `type X = ...`, genéricos PEP 695, `match`, `dataclass(slots=True, frozen=True)` y `typing.override`.
*Alternativa*: `pip` + `requirements.txt` como usage-monitor. Se descarta: `uv` resuelve y fija más rápido, y con hashes. `httpx` en lugar de `requests` también se descarta: sigue en 0.x y aquí no aporta nada (el cliente es síncrono y va en su propio hilo).
*Alternativa*: Tauri o Electron. Se descartan porque el usuario eligió explícitamente el stack de usage-monitor.

### D2. Estructura del paquete
```
pr_watch/
  __main__.py          arranque: instancia única, config, credencial, app
  app.py               cableado: hilos, temporizador, puente con la interfaz
  config.py            carga/validación/escritura de config.toml
  credential.py        keyring + respaldo a archivo + PR_WATCH_TOKEN/.env
  providers/
    base.py            modelo neutro (dataclasses), Protocol del proveedor, errores
    github.py          proveedor de GitHub (GraphQL)
    __init__.py        registro {"github": GitHubProvider}
  polling.py           diferencia entre sondeos, novedades, caducidad, purga (puro)
  state_store.py       estado persistido por proveedor, escritura atómica
  view.py              modelo de vista para panel y tooltip (puro)
  notify.py            hechos notificables, deduplicación, emisión
  icon.py              glifo de PR + punto, con Pillow; también genera el .ico
  tray.py              pystray: icono, menú, clic
  windows.py           ventanas pywebview: panel y ajustes, API expuesta a JS
  placement.py         posición del panel junto al icono / área de trabajo
  autostart.py         clave Run / .desktop
  single_instance.py   mutex/lock + canal para "muestra tu panel"
  theme.py             tema de la barra de tareas (color del glifo)
  log.py               log rotativo en el directorio de configuración
  ui/
    panel.html  panel.css  panel.js
    settings.html  settings.js
    icons.css          glifos Segoe con respaldo SVG
    preview/           index.html (selector de escenario y tema)
  preview.py           genera los escenarios desde view.py y sirve ui/ en localhost
tests/
build.py               PyInstaller + generación del .ico
```

### D3. Modelo neutro y contrato del proveedor
`providers/base.py` define `PullRequest` (dataclass inmutable con los campos de `forge-provider`), `Relation` (AUTHOR > REVIEWER > ASSIGNEE), `ChecksState`, `PrState`, y un `Protocol`:
- `verify(scope, token) -> Identity` (lanza `InvalidCredential`, `ScopeInaccessible`, `RateLimited(reset_at)`, `NetworkError`)
- `fetch_open(scope, token) -> FetchResult` (`prs`, `complete: bool`)
- `fetch_states(ids, token) -> dict[id, PrState | INACCESSIBLE]`
- `block_url(scope, relation) -> str`
- `vocabulary` (`"PR"`, prefijo `#`)

`scope` es opaco para el resto de la aplicación: en GitHub es la organización; en GitLab será la URL de instancia más un grupo opcional. El identificador del modelo es el `node_id` global de GitHub, que sobrevive a renombres de repositorio.

### D4. GraphQL en lugar de REST
Una sola petición `POST /graphql` con tres búsquedas con alias (`author:@me`, `review-requested:@me`, `assignee:@me`, todas con `org:<org> is:pr is:open archived:false`) trae lo que el panel necesita: `isDraft`, `mergeable`, `reviewDecision`, `latestOpinionatedReviews` (una revisión vigente por revisor), `commits(last:1).statusCheckRollup.state`, `reviewThreads.isResolved`, autor, repositorio y `updatedAt`. Si alguna búsqueda tiene más páginas, se piden solo las páginas de esa búsqueda. Los pull requests que desaparecen se consultan con `nodes(ids: [...])`.
*Alternativa*: REST con `GET`, que exigiría una llamada de reviews, una de checks y una de hilos por cada PR (los hilos sin resolver ni siquiera existen en REST). Por eso desaparece el sondeo de detalle de mr-watch.
*Garantía de solo lectura*: `github.py` tiene un único punto de envío que analiza el documento: si contiene la palabra `mutation` o `subscription` fuera de cadenas, lanza `AssertionError` sin emitir nada. Las consultas son constantes del módulo; ninguna se construye por concatenación con datos del usuario. La organización viaja como variable GraphQL.

### D5. Reglas de traducción en GitHub
- Aprobaciones: revisores con su revisión vigente en `APPROVED`.
- Cambios pedidos: alguna revisión vigente en `CHANGES_REQUESTED`.
- Checks: `SUCCESS` → correcto; `FAILURE`/`ERROR` → fallido; `PENDING`/`EXPECTED` → en curso; sin rollup → ninguno.
- Conflictos: `mergeable == CONFLICTING`. Con `UNKNOWN` se conserva el valor anterior del estado persistido (el escenario de fusionabilidad desconocida).
- Listo para fusionar: no borrador, sin conflictos, checks correctos o ninguno, sin cambios pedidos, y `reviewDecision == APPROVED` o (sin `reviewDecision` y al menos una aprobación).
- "Te toca": el PR vino por la búsqueda `review-requested:@me`.

### D6. Concurrencia
- Hilo principal: `webview.start()`, que exige el hilo principal. Ahí viven el panel (creado oculto al arrancar, para que abrirlo sea instantáneo) y la ventana de ajustes (creada bajo demanda y destruida al cerrarse).
- Hilo de bandeja: `pystray.Icon.run()` en un hilo propio en Windows. En Linux ambos usan el bucle de GTK; se sigue el patrón de usage-monitor (`run_detached` dentro del bucle de GTK) y la tarea 1.2 lo comprueba antes de construir el resto.
- Hilo de sondeo: bucle con `threading.Event.wait(intervalo)`; "actualizar ahora" hace `set()` sobre el evento; un `Lock` impide sondeos concurrentes.
- Hilo de notificaciones: un bucle `asyncio` propio para `desktop-notifier`.
- El estado compartido (último resultado, contador, marcas) vive en un objeto con `Lock`. Cada cambio produce un modelo de vista nuevo, que se envía al panel con `window.evaluate_js("render(" + json.dumps(vm) + ")")`. `json.dumps` produce un literal JS válido, así que los títulos de PR no pueden inyectar código.

### D7. Puente Python ↔ JS
`windows.py` expone a JS un objeto `js_api` con métodos pequeños: `refresh()`, `open_url(url)` (solo `https://github.com/...` del proveedor activo; cualquier otra URL se ignora), `toggle_pin()`, `hide()`, `open_settings()`, `blur()`, `settings_load()`, `settings_verify(scope, token)`, `settings_save(payload)`, `settings_logout()`, `open_config_file()`. El token entra de JS a Python en `verify` y `save`, pero nunca sale de Python hacia JS: `settings_load()` solo devuelve `has_token: bool`.
La pérdida de foco la detecta JS (`window` `blur`) y llama a `blur()`; Python decide si ocultar según el fijado y si la ventana de ajustes está abierta.

### D8. Estética
`panel.css` reproduce el popup de usage-monitor con variables CSS: en oscuro, fondo `#2b2b2b`, texto `#e6e6e6`, encabezados `#9a9a9a` 11.5px en negrita y mayúsculas, separadores `#3d3d3d` y enlaces `#5aa0ff`; en claro, la paleta equivalente. El tema se elige con `prefers-color-scheme`, que WebView2 y WebKitGTK derivan del sistema y que cambia en caliente. Los colores de estado son verde `#3fb950`, ámbar `#d29922`, rojo `#e5534b` y gris `#8a8a8a`. La tipografía es `"Segoe UI", system-ui`. Los iconos de acción usan `"Segoe Fluent Icons", "Segoe MDL2 Assets"` con los puntos de código de mr-watch; si la fuente no existe (Linux), se usa un SVG equivalente embebido en `icons.css`. El maquetado de referencia aprobado es la opción A del brainstorming (`.superpowers/brainstorm/*/content/panel-v2.html`).
El alto del panel lo mide JS (`document.body.scrollHeight`) tras cada `render` y lo comunica a Python, que redimensiona y recoloca la ventana.

### D9. Posición del panel
En Windows: `Shell_NotifyIconGetRect` vía `ctypes` con el `hwnd` y el `uID` del icono de pystray (atributos internos de su backend win32, aislados en `placement.py`). Si falla, se usa la esquina del área de trabajo (`SPI_GETWORKAREA`) del lado de la barra de tareas. En Linux: esquina superior o inferior derecha según el panel del escritorio, o centrado si no puede saberse. Todo en píxeles físicos, teniendo en cuenta el DPI.

### D10. Icono de bandeja
`icon.py` dibuja con Pillow a 4× y reduce con LANCZOS: el glifo de pull request (dos nodos con su rama y la flecha de vuelta), en blanco o en `#1f1f1f` según `theme.py` (en Windows lee `SystemUsesLightTheme`; en Linux, blanco). El punto de novedades es un círculo azul `#2f81f7` con borde del color opuesto al glifo, en la esquina superior derecha. Solo se entrega una imagen nueva a pystray cuando cambia la tupla (tema, hay_novedades). `build.py` usa la misma función para generar `pr-watch.ico` (16–256 px) en un directorio temporal antes de llamar a PyInstaller.

### D11. Credencial
`keyring` con servicio `pr-watch` y usuario `github` (el nombre del proveedor). Si el backend activo es `keyring.backends.fail.Keyring` o falla la escritura, se usa `token-<proveedor>` en el directorio de configuración, creado con `os.open(..., 0o600)` y con aviso. El orden de lectura es: `PR_WATCH_TOKEN`, `.env` del directorio de trabajo, keyring y archivo. El objeto que guarda el token redefine `__repr__` para no mostrarlo.

### D12. HTTP y TLS
Un único `requests.Session` con `truststore.inject_into_ssl()` al arrancar, para que la verificación use el almacén de CA del sistema y no `certifi`. El proxy del sistema lo toma `requests` a través de `urllib.request.getproxies()`, que en Windows lee el registro. Timeout de 15 s. Los errores se clasifican así: 401 → `InvalidCredential`; errores GraphQL de tipo `NOT_FOUND`/`FORBIDDEN` sobre la organización → `ScopeInaccessible`; 403/429 con `x-ratelimit-remaining: 0` o `retry-after` → `RateLimited`; el resto → `NetworkError`.

### D13. Estado persistido
`state-github.json` en el directorio de configuración: por cada PR, la instantánea de los campos que definen novedad, el instante en que pasó a terminal y los hechos ya notificados. Se escribe con archivo temporal más `os.replace`. Incluye una versión de esquema; si la versión no coincide o el JSON no se puede leer, se descarta.

### D14. Instancia única
En Windows, mutex con nombre `Local\pr-watch`; en Linux, `fcntl.flock` sobre un archivo de bloqueo. La primera instancia escucha en un `multiprocessing.connection.Listener` (tubería con nombre o socket Unix con `authkey` aleatoria guardada en el directorio de configuración). La segunda envía `show` y termina.

### D15. Notificaciones
`desktop-notifier` emite toasts en Windows y notificaciones por D-Bus en Linux, con un callback al pulsarlas que abre la URL o el panel. Si falla, se registra una vez y se desactiva la emisión hasta el siguiente cambio de preferencia.

### D16. Vista previa
`python -m pr_watch.preview` construye los escenarios con modelos de ejemplo pasados por `view.py` (así no se desincronizan), los escribe como `ui/preview/scenarios.json` y sirve `pr_watch/ui/` en `127.0.0.1` con `http.server`. `panel.js` detecta que no existe `window.pywebview` y usa un `js_api` falso que registra las llamadas en la consola.

### D17. Empaquetado
`uv run build.py` construye para la plataforma en la que corre, porque PyInstaller no compila de forma cruzada. La versión vive en `pr_watch/__init__.py`.
- **Windows**: genera `pr-watch.ico` desde `icon.py` y ejecuta PyInstaller `--onefile --windowed` con `pr_watch/ui` como datos, el icono y un recurso de versión. Resultado: `dist/pr-watch.exe`. WebView2 viene con Windows 10/11 y no se empaqueta.
- **Linux**: ejecuta PyInstaller `--onefile` con `pr_watch/ui` como datos. Resultado: `dist/pr-watch`. `PyGObject` entra como dependencia de Python (solo en Linux, con marcador `sys_platform == 'linux'` en `pyproject.toml`) y PyInstaller lo empaqueta con sus *hooks* de `gi`. GTK 3, WebKit2GTK 4.1 y Ayatana AppIndicator se excluyen del empaquetado y se toman del sistema: llevarlos dentro haría el binario enorme y frágil entre distribuciones. Se construye en la distribución más antigua que se quiera soportar (Ubuntu 22.04 como referencia), porque el binario hereda su versión de glibc; desde esta máquina vale WSL con Ubuntu 22.04. Al arrancar, `__main__.py` intenta `gi.require_version` de cada biblioteca y, si falta alguna, muestra qué paquete instalar (`gir1.2-webkit2-4.1`, `gir1.2-ayatanaappindicator3-0.1`) y termina.
- El icono de la ventana en Linux se entrega en tiempo de ejecución desde `icon.py`, y el `.desktop` de autoarranque apunta al binario.

## Risks / Trade-offs

- [pystray + pywebview en Linux comparten GTK y pueden bloquearse] → Tarea 1.2: un spike mínimo que abre el icono y un panel oculto en ambos sistemas antes de construir encima; se adopta el patrón de usage-monitor.
- [AppIndicator no entrega el clic ni muestra el tooltip] → El menú lleva `Abrir pr-watch` como primera entrada (especificado en `tray-menu`). El tooltip se especifica "donde el sistema lo soporte".
- [Los permisos de checks pueden no estar disponibles para fine-grained tokens, y `statusCheckRollup` saldría vacío] → Con `null` el estado de checks se trata como "ninguno", no como error. La tarea 3.6 lo comprueba con un token real y, si hace falta, ajusta la lista de permisos que muestra la ventana de ajustes.
- [La organización puede exigir aprobación de fine-grained tokens] → La verificación lo distingue como `ScopeInaccessible`, con un mensaje que lo explica.
- [La API de búsqueda tiene un límite secundario (30/min)] → Un sondeo usa una sola petición con tres alias; el suelo de 30 s y la suspensión hasta `reset_at` lo mantienen lejos.
- [El toast de Windows sin AUMID registrado puede no activar el callback tras cerrarse la app] → Solo importa con la app corriendo, que es el caso; se acepta.
- [`Shell_NotifyIconGetRect` depende de atributos privados de pystray] → Aislado en `placement.py`, con respaldo al área de trabajo.
- [Un `.exe` de PyInstaller de unos 15 MB frente a los 4 MB de mr-watch] → Aceptado: es el precio de iterar rápido.

## Migration Plan

No aplica: es una aplicación nueva que convive con mr-watch, con identificadores distintos (`pr-watch` en configuración, keyring, autoarranque y mutex).
