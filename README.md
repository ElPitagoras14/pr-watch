# pr-watch

Vigila los pull requests que te involucran y los deja visibles en la bandeja del sistema. Solo lectura. Habla con **GitHub** o con **GitLab** —la nube o una instancia propia—, una forja a la vez, y se cambia de una a otra desde la ventana de ajustes.

```
┌──────────────────────────────────────────┐
│ PR Watch                     ⟳  ⚙  📌  ✕ │
│ CUENTA                                   │
│ Usuario                        miusuario │
│ Proveedor          github.com · contoso │
│ Estado                         Conectado │
│ ──────────────────────────────────────── │
│ MÍOS · 3                       Ver todos │
│ ● #131 Logs de auditoría      conflictos │
│   contoso/audit · checks ✗ · 0 sin res… │
│ ● #142 Fix ruta estática    aprobado (2) │
│   contoso/netops · checks ✓ · 0 sin r…  │
│ ──────────────────────────────────────── │
│ POR REVISAR · 1                Ver todos │
│ ● #150 Utilidades de red              te toca │
│   contoso/drivers · de @colega · hace 3 h│
│ ──────────────────────────────────────── │
│ Actualizado hace 12 s              0.1.0 │
└──────────────────────────────────────────┘
```

Un panel que sale en la esquina de la pantalla junto a la bandeja, con la estética del de [usage-monitor-for-claude](https://github.com/jens-duttke/usage-monitor-for-claude). Arriba lo tuyo, abajo lo que esperan de ti. Cada PR ocupa dos líneas: título y estado arriba; repositorio, checks y conversaciones sin resolver (o autor y antigüedad, si es para revisar) debajo.

El icono de bandeja es el glifo de un pull request, claro u oscuro según tu barra de tareas. Le aparece un **punto azul** cuando ha pasado algo desde la última vez que abriste el panel, y desaparece al abrirlo.

El panel se oculta al perder el foco, salvo que lo fijes con el icono de fijar. La ✕ y Escape lo esconden, no cierran la aplicación: para salir, `Salir` desde el menú del icono.

Es la versión para GitHub y GitLab de mr-watch, rehecha en Python para poder iterar rápido sobre la interfaz.

## Qué vigila

Los pull requests (o *merge requests*) abiertos de **un ámbito**: una organización de GitHub o un grupo de GitLab —con sus subgrupos—, o tus repositorios personales; donde apareces de alguna de estas tres formas: los creaste tú (`author:@me`), tienes la revisión pedida, a ti o a un equipo tuyo (`review-requested:@me`), o te los asignaron (`assignee:@me`). De cada uno se muestran las aprobaciones, los cambios pedidos, los checks, los conflictos y las conversaciones sin resolver. Los borradores no salen. Los fusionados o cerrados se quedan 15 minutos y luego desaparecen.

Quién aprobó se ve al detenerse sobre la fila. Las aprobaciones se muestran como `aprobado (2)`, nunca `2/2`: el número requerido depende de reglas de protección que no siempre son visibles, e inventarlo daría un dato con aspecto oficial que no lo es.

## Qué NO hace

No aprueba, no comenta y no fusiona. La API GraphQL se consulta por `POST`, así que la garantía no puede ser "solo `GET`": es doble. El token se pide **sin permisos de escritura**, y el cliente se niega a enviar cualquier documento que contenga una `mutation`.

## Instalación

Los dos ejecutables están en el [último release](https://github.com/ElPitagoras14/pr-watch/releases/latest).

### Windows

Descarga [`pr-watch.exe`](https://github.com/ElPitagoras14/pr-watch/releases/latest) y ejecútalo. Es un único archivo portable: no hay instalador ni hace falta Python.

El `.exe` oficial va firmado (Authenticode) con un certificado autofirmado de Telconet: en Propiedades → Firmas digitales aparece el nombre del editor. Fuera de la red de Telconet, hasta que IT distribuya el certificado por GPO como raíz de confianza, Windows SmartScreen puede seguir avisando al abrirlo igual que con un `.exe` sin firmar — ver [`docs/firma-de-codigo.md`](docs/firma-de-codigo.md) para el procedimiento de generación del certificado.

### Linux

Descarga [`pr-watch`](https://github.com/ElPitagoras14/pr-watch/releases/latest), dale permiso de ejecución (`chmod +x pr-watch`) y ejecútalo. El binario oficial se construye en Ubuntu 24.04 y lleva dentro Python, sus dependencias y su propio glib, así que del sistema necesita **glibc 2.38 o más nueva** (Ubuntu 23.10+, Debian 13+, Fedora 39+) más GTK, WebKit y el indicador de bandeja. En una distribución más antigua hay que construirlo allí. En Debian/Ubuntu:

```
sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-ayatanaappindicator3-0.1
```

Si falta alguno, la aplicación lo dice al arrancar y nombra el paquete. En escritorios donde el clic sobre el icono abre el menú, el panel se abre con la primera entrada, `Abrir pr-watch`.

### Arrancar con la sesión

Viene **apagado**, como en usage-monitor: se activa y se desactiva con la entrada `Arrancar con la sesión` del menú del icono. Por debajo es una entrada en la clave `Run` del usuario en Windows, o un `.desktop` en `~/.config/autostart` en Linux. Nada a nivel de máquina. Si mueves el ejecutable con el autoarranque activado, la entrada se corrige sola la próxima vez que lo abras. Si la borras a mano, el menú lo refleja.

Para desinstalar: desactiva `Arrancar con la sesión`, sal y borra el ejecutable. La configuración queda en el directorio indicado más abajo, por si vuelves.

### El token

#### GitHub

Crea un [*fine-grained personal access token*](https://github.com/settings/personal-access-tokens/new) con:

- **Resource owner**: la organización, o tu cuenta si quieres vigilar tus repositorios personales.
- **Repository access**: los repositorios que quieras vigilar.
- **Permisos**, todos de **solo lectura**: *Pull requests*, *Metadata*, *Commit statuses* y *Checks*.

Si la organización exige aprobar los tokens, hasta que lo aprueben la aplicación dirá que no tiene acceso a la organización. No es lo mismo que un token inválido, y por eso lo distingue.

#### GitLab

Crea un *personal access token* en `<tu instancia>/-/user_settings/personal_access_tokens` con un único ámbito: **`read_api`**. El enlace `Crear token` de la ventana de ajustes abre esa página en la instancia que tengas seleccionada.

Hace falta **GitLab 16 o posterior**; la verificación consulta la versión de la instancia y, si es anterior, lo dice con la versión encontrada en lugar de fallar más tarde con un error críptico. Funciona igual en Community y en las ediciones de pago: el cliente solo pide campos que existen en Community.

Si la instancia es propia y presenta un certificado de una CA corporativa, basta con que esa CA esté en el almacén del sistema; la aplicación lo usa tal cual y no ofrece desactivar la verificación TLS.

#### El recorrido

La primera vez la aplicación arranca a la bandeja sin pedir nada. Al abrir el panel sale también la ventana de ajustes. Eliges el proveedor —y, con GitLab, la dirección de la instancia: `https://gitlab.com` o la tuya—, pegas el token y pulsas `Verificar token`, que responde `Conectado como <usuario>` y llena la lista de ámbitos que ve ese token: organizaciones en GitHub, grupos en GitLab. La primera opción es siempre tu **cuenta o espacio personal** (solo tus repositorios); el resto, organizaciones o grupos (por su ruta completa, subgrupos incluidos). Eliges una, se comprueba el acceso, y guardas; no hace falta reiniciar. Un *fine-grained token* no puede listar organizaciones (GitHub le devuelve siempre una lista vacía), así que en ese caso se deducen de los repositorios a los que el token tiene acceso: con la organización como dueña del token, aparece ella. Si aun así no aparece, la opción `Otro (escribir a mano)…` deja escribir el nombre.

Cambiar de forja y volver no obliga a reconfigurar: **cada una guarda su token y su ámbito por separado**, y el panel no mezcla lo de una con lo de la otra. Dos instancias distintas de GitLab también cuentan como forjas distintas.

El token vive en el almacén de credenciales del sistema, bajo el servicio `pr-watch`, con una entrada por forja (`github`, `gitlab@gitlab-telconet-ec`…). Donde no hay almacén (Linux sin Secret Service), va a un archivo con permisos `600`, y la ventana de ajustes avisa de que quedó en texto plano. Para desarrollo también se acepta en la variable `PR_WATCH_TOKEN` o en un `.env` del directorio de trabajo; con varias forjas conviene la variable propia de cada una (`PR_WATCH_TOKEN_GITHUB`, `PR_WATCH_TOKEN_GITLAB_GITLAB_TELCONET_EC`…), que gana a la genérica. `GITHUB_TOKEN` y `GH_TOKEN` se ignoran a propósito, porque suelen tener permisos de escritura.

## Configuración

Lo habitual se cambia en la ventana de ajustes: proveedor, instancia, ámbito y token, cada cuánto se consulta, el tope por bloque y las notificaciones. Lo que se guarda ahí surte efecto sin reiniciar.

Por debajo está `config.toml`, en `%APPDATA%\pr-watch` en Windows o `~/.config/pr-watch` en Linux:

```toml
provider = "github"
poll_interval_secs = 60   # mínimo 30
max_per_block = 5         # de CADA bloque, de 1 a 20
closed_ttl_minutes = 15   # cuánto sigue visible un PR fusionado o cerrado
notifications = false

[github]
org = "contoso"     # o, para tus repositorios personales:
# user = "miusuario"

[gitlab]
host = "https://gitlab.com"   # o la instancia propia: https://gitlab.empresa.com
group = "empresa/plataforma"  # admite subgrupos; o, para tu espacio personal:
# user = "miusuario"
```

`provider` decide cuál de las dos tablas se usa. Las dos se conservan siempre en el archivo, así que ir y volver entre forjas no obliga a reescribir el ámbito. Un `host` que no sea una dirección utilizable deja la aplicación sin sondear y lo avisa, en lugar de consultar a ciegas.

Un `config.toml` con errores de sintaxis **no impide arrancar**: se usan los valores por defecto y tu archivo se deja intacto.

Las notificaciones vienen apagadas. Si las activas, solo avisan de lo accionable: un PR tuyo queda listo para fusionar, se rompe por conflictos o checks, o te piden cambios; o te llega un PR a revisar. Cada hecho se avisa una vez, y si en una misma consulta hay más de tres, llegan en un solo aviso.

## Desarrollo

Hace falta [uv](https://docs.astral.sh/uv/). El proyecto usa Python 3.13.

```
uv sync                                       # entorno y dependencias
uv run python -m pr_watch                     # la aplicación
uv run python -m unittest discover -s tests   # pruebas
uv run ruff check && uv run pyright           # estilo y tipos
uv run python -m pr_watch.preview             # la interfaz en el navegador
uv run build.py                               # el ejecutable de esta plataforma
```

La **vista previa** abre el panel y la ventana de ajustes en el navegador, con escenarios de ejemplo (sin configurar, vacío, por encima del tope, todos los estados, novedades, datos desactualizados, límite agotado) y alternancia de tema. Usa los mismos archivos de `pr_watch/ui/` que la aplicación: retocas el CSS, recargas y lo ves.

`PR_WATCH_CONFIG_DIR` cambia el directorio de configuración, para probar sin tocar el real. `PR_WATCH_DEBUG=1` sube el registro a nivel de depuración, y `PR_WATCH_DEVTOOLS=1` abre las herramientas de desarrollo de las ventanas.

Para comprobar el token y los permisos contra la forja sin la interfaz:

```
uv run python -m pr_watch.providers.github --check
uv run python -m pr_watch.providers.gitlab --check
```

El ejecutable de Linux se construye en Linux; desde Windows vale WSL. El binario solo funciona en distribuciones con una glibc igual o más nueva que la del sistema donde se construyó, así que conviene construirlo en la más antigua que se quiera soportar.

### Publicar una versión

Publicar es **subir la versión y fusionar a `main`**. No hay que crear tags ni releases a mano:

1. Sube la versión en los dos sitios donde vive, `pyproject.toml` y `pr_watch/__init__.py`. `tests/test_version.py` falla si divergen, y `python scripts/release_version.py` imprime la versión o dice qué está mal.
2. Fusiona a `main`.

A partir de ahí, el workflow `release` encadena cuatro etapas: **check-version → build → tag → release**. `check-version` compara la versión con los tags existentes; si el tag `v<versión>` ya existe, el pipeline termina en verde sin hacer nada, así que los pushes que no suben la versión no cuestan casi nada. Si no existe, corre las pruebas, el estilo y los tipos; construye `pr-watch.exe` en Windows y `pr-watch` en Ubuntu 24.04; crea el tag anotado `v<versión>`; y publica el release con los dos binarios adjuntos.

Nada se publica desde un commit que no pasa la verificación, y el tag no se crea hasta que los dos binarios existen.

**Si una ejecución deja el tag creado pero sin release** —falla el último paso—, relanzarla no sirve: `check-version` verá el tag y dirá que no hay nada que publicar. Hay dos salidas: borrar el tag (`git push origin :refs/tags/vX.Y.Z`) y volver a lanzar, o crear el release a mano desde los artefactos de esa ejecución con `gh release create vX.Y.Z pr-watch.exe pr-watch`.

### Otros proveedores

Todo lo que no es `pr_watch/providers/` trabaja con un modelo neutro de pull request, y el vocabulario de la interfaz lo pone el proveedor (`PR` y `#142` en GitHub, `MR` y `!142` en GitLab). Añadir una forja más consiste en escribir otro módulo que cumpla el contrato de `providers/base.py` y registrarlo en `providers/__init__.py`.

El de GitLab tiene dos detalles que conviene saber antes de tocarlo:

- **La introspección del esquema no es de fiar**: la instancia responde con un esquema cacheado que anuncia campos que luego rechaza al ejecutarlos. Lo que vale es ejecutar la consulta.
- **El límite que aprieta es la complejidad**, 250 por petición, no la paginación (100 nodos). El documento de sondeo marca 169 con página de 50; cada campo nuevo lo acerca al techo, así que pide `queryComplexity` y avisa en el registro al pasar del 80 %.
