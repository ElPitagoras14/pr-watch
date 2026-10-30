## Why

mr-watch resuelve bien "qué merge requests me esperan" desde la bandeja, pero está escrito en Rust con egui, e iterar sobre su interfaz es lento: cada retoque visual pasa por una compilación. Hace falta lo mismo para **pull requests de GitHub**, y conviene hacerlo con el stack de usage-monitor-for-claude (Python + pystray + pywebview), donde el panel es HTML/CSS y se puede retocar viéndolo al instante.

## What Changes

- Nueva aplicación de bandeja **pr-watch**, réplica funcional de mr-watch para pull requests de **github.com**: vigila los PR abiertos de una organización en los que el usuario es autor, revisor solicitado o asignado.
- Mismo alcance que mr-watch: panel junto al icono con dos bloques (propios / por revisar), ventana de ajustes con verificación del token, token en el almacén de credenciales, sondeo periódico, estado persistido, detección de novedades, notificaciones opcionales, autoarranque, `config.toml`, Windows y Linux.
- **Diferencias deliberadas con mr-watch**:
  - Stack: Python 3.13 con las versiones más recientes compatibles de cada paquete, gestionado con `uv`; `pystray`, `pywebview`, `requests`, `keyring`, `Pillow`; empaquetado con PyInstaller como **ejecutable único y portable en las dos plataformas**: `pr-watch.exe` en Windows y `pr-watch` (ELF) en Linux. Ninguno necesita Python instalado.
  - El panel y la ventana de ajustes son HTML/CSS/JS dentro de pywebview, con la estética del popup de usage-monitor-for-claude (fondo oscuro, secciones en mayúsculas grises, pares etiqueta/valor, separadores finos, pie "Actualizado hace…"). mr-watch prohibía WebViews; aquí son precisamente el motivo del cambio.
  - Cada PR ocupa dos líneas: título y estado arriba; repositorio, checks y conversaciones sin resolver debajo, en gris.
  - El icono de bandeja deja de ser un disco teñido por estado con número: es un **glifo monocromo de pull request**, estático, con un **punto** cuando hay novedades sin ver. El color de estado vive solo en el panel.
  - Acceso a la forja detrás de una **capa de proveedor**: el resto de la aplicación solo conoce un modelo neutro. GitHub es el único proveedor ahora; GitLab (cloud o self-hosted) debe poder añadirse como otro proveedor sin tocar panel, bandeja ni sondeo.
  - Token: *fine-grained personal access token* de GitHub con la organización como dueño y permisos de solo lectura.
  - Un solo ritmo de sondeo en lugar de dos: la API GraphQL de GitHub devuelve en una sola consulta el listado con revisiones, checks, conflictos y conversaciones, así que el ritmo de "detalle" de mr-watch, que existía porque el listado de GitLab no traía aprobaciones ni pipeline, sobra.
  - "Solo lectura" ya no puede significar "solo `GET`": GraphQL se consulta por `POST`. La garantía pasa a ser doble: el token no tiene permisos de escritura y el cliente se niega a enviar cualquier documento GraphQL que no sea una `query`.
  - El autoarranque es opcional y viene apagado, como en usage-monitor: se activa desde la entrada `Arrancar con la sesión` del menú de bandeja. mr-watch se registraba por su cuenta.
  - El panel puede abrirse en un navegador normal con datos de ejemplo para iterar sobre el CSS sin arrancar la aplicación.

## Capabilities

### New Capabilities
- `app-config`: `config.toml`, valores por defecto, límites, autoarranque y acceso desde la ventana de ajustes.
- `credential-storage`: token en el keyring del sistema, respaldo a archivo, origen por entorno en desarrollo, borrado.
- `forge-provider`: modelo neutro de pull request y contrato que debe cumplir cualquier proveedor de forja; elección del proveedor por configuración.
- `github-client`: proveedor de GitHub de solo lectura: autenticación, búsqueda por relación, detalle de revisiones, checks y conversaciones.
- `pr-polling`: sondeo periódico, estado persistido, detección de novedades, filtrado de ruido y purga.
- `main-window`: el panel junto al icono: secciones, filas de dos líneas, acciones, fijado, tema, marcas de novedad.
- `settings-window`: ventana de ajustes con verificación de credencial, ajustes con control propio y cierre de sesión.
- `tray-menu`: icono y menú de bandeja con las acciones fijas.
- `unseen-counter`: novedades sin ver como punto sobre el icono y tooltip.
- `notifications`: notificaciones del sistema opcionales y solo de lo accionable.
- `app-icon`: marca propia dibujada por código para bandeja, ventana y ejecutable.
- `panel-preview`: vista del panel en un navegador con datos de ejemplo, para iterar sobre la interfaz.
- `packaging`: el resultado es un ejecutable único por plataforma (`.exe` en Windows, binario en Linux) que no requiere Python.

### Modified Capabilities
<!-- Proyecto nuevo: no hay especificaciones previas en este repositorio. -->

## Impact

- Repositorio nuevo `pr-watch`, sin código previo. mr-watch (`mr-watch`) es la referencia de comportamiento; usage-monitor-for-claude, la de stack y estética.
- Dependencias de ejecución: `requests`, `truststore`, `pystray`, `pywebview`, `Pillow`, `keyring`, `tomli-w`, `desktop-notifier` (versiones exactas en `design.md`, D1). En Linux, el binario necesita en el sistema GTK 3, WebKit2GTK 4.1 y Ayatana AppIndicator, igual que usage-monitor; el resto va dentro.
- Dependencias de desarrollo: `pyinstaller`, `pyright`, `ruff`; entorno y bloqueo con `uv`.
- API externa: GraphQL v4 de GitHub (`api.github.com/graphql`), solo consultas, nunca mutaciones.
