## Context

`pr-watch` ya está partido en dos mitades: `pr_watch/providers/` conoce la forja, y todo lo demás —sondeo, estado persistido, panel, bandeja, notificaciones— trabaja solo con el modelo neutro de `providers/base.py`. El registro de `providers/__init__.py` existe desde el primer día con una sola entrada, y `config.toml` ya lleva la clave `provider`.

Lo que falta es real pero acotado:

- No hay proveedor de GitLab.
- `providers.create(name)` solo recibe un nombre: no hay forma de decirle a un proveedor contra qué instancia hablar.
- La credencial (`CredentialStore(provider, ...)`) y el estado (`state_store.path_for(dir, provider)`) se identifican por el nombre del proveedor, que no distingue dos instancias de GitLab.
- `App` ata proveedor, credencial, estado y sondeo **una sola vez**, en `__init__`. `settings_save` sabe cambiar ajustes y token, no la forja.
- La ventana de ajustes tiene GitHub escrito a fuego: `settings_model.load` importa `providers.github` directamente, y `settings.html` dice "Crear token en GitHub", "fine-grained token", "Organización" y "Máximo de PR por bloque".

Restricciones heredadas que este diseño respeta: solo lectura (ningún documento GraphQL con `mutation`), el token nunca sale hacia la interfaz ni al registro, TLS siempre verificado contra el almacén del sistema (`truststore`), y la interfaz no inventa vocabulario: lo pide al proveedor.

### Validado contra la instancia real

Las decisiones de este documento no son de catálogo: se comprobaron ejecutando consultas contra `gitlab.telconet.ec`, que corre **GitLab CE 19.2.7** (`metadata { version enterprise }` devuelve `enterprise: false`). De ahí salen tres hechos que cambiaron el diseño:

1. **La introspección del esquema no es fiable**: la instancia responde a cualquier consulta con campos de introspección devolviendo un esquema completo cacheado, que incluye campos que luego rechaza al ejecutarlos. Lo que vale es lo que acepta el validador al ejecutar.
2. **La edición importa más que la versión**: `approvalsRequired`, `approvalsLeft` y `changeRequesters` existen en el esquema pero **no en una instancia CE**. El proveedor usa solo campos disponibles en CE, que también están en EE.
3. **El límite que aprieta es la complejidad, no la paginación**: el máximo de página son 100 nodos, pero el presupuesto de complejidad es 250 por petición y el documento de sondeo lo consume casi entero si no se cuidan los campos.

## Goals / Non-Goals

**Goals**

- Un proveedor `gitlab` de solo lectura que sirva igual a `gitlab.com` y a una instancia propia.
- Que proveedor e instancia se elijan desde Ajustes y el cambio se aplique sin reiniciar.
- Que cada instancia tenga su credencial y su estado, sin mezclarse.
- Que nada fuera de `providers/` gane una rama `if gitlab:`.

**Non-Goals**

- Dos forjas activas a la vez.
- Instancias anteriores a GitLab 16.
- Configurar una CA propia o desactivar la verificación TLS desde la aplicación.
- Tocar el comportamiento del proveedor de GitHub más allá de lo que exija el contrato nuevo.

## Decisions

### 1. Un solo proveedor `gitlab` con host configurable, no `gitlab-cloud` y `gitlab-selfhosted`

La nube y una instancia propia hablan la misma API; lo único que cambia es el origen. Dos entradas en el registro duplicarían el módulo entero para parametrizar una URL.

- *Alternativa descartada*: dos proveedores. Multiplica el código y obliga al usuario a elegir entre dos cosas que para él son "GitLab".
- *Consecuencia*: el host deja de ser una constante del módulo y pasa al constructor, así que `providers.create` necesita la configuración, no solo un nombre.

### 2. `create(cfg)` en lugar de `create(name)`

El registro pasa a ser `dict[str, Callable[[Config], Provider]]` y `create(cfg)` construye el proveedor con lo que necesite de su tabla (`[gitlab] host`). GitHub ignora el argumento.

- *Alternativa descartada*: un `configure(host)` posterior a la creación. Deja al proveedor existir a medio construir.
- *Ciclo de importación*: `providers/` importaría `config`, que no importa `providers`. No hay ciclo.

### 3. GraphQL contra `<host>/api/graphql`, mínimo GitLab 16, campos de CE

Es lo que permite traer en una respuesta aprobaciones, pipeline, conflictos y discusiones sin resolver, sin una petición por merge request —la misma garantía que ya da el proveedor de GitHub y de la que depende el intervalo de 30 s.

- *Alternativa descartada*: REST v4. Más compatible con instancias viejas, pero el listado de merge requests no trae aprobaciones ni conteo de discusiones sin resolver: serían N+1 peticiones por ciclo y datos más pobres (`blocking_discussions_resolved` es un sí/no, no un número).
- *Verificación de la instancia*: `metadata { version enterprise }` —comprobado que responde con un token `read_api`—. Si la versión es anterior a 16, la verificación lo dice con la versión encontrada en lugar de dejar que falle un campo desconocido con un error de GraphQL ilegible.
- *Solo campos de CE*: los tres campos de pago (`approvalsRequired`, `approvalsLeft`, `changeRequesters`) quedan fuera del documento. Ninguno hace falta: el modelo neutro no tiene denominador de aprobaciones, y los cambios pedidos salen del estado de revisión de cada revisor, que sí está en CE.
- *Red de seguridad*: si la instancia rechaza un campo (`undefinedField`), el proveedor lo traduce a un error que nombra el campo y la versión de la instancia, en vez de propagar el error crudo de GraphQL.

### 4. Una sola forma de consulta: las tres conexiones de `currentUser`

Comprobado en la instancia: `authoredMergeRequests`, `assignedMergeRequests` y `reviewRequestedMergeRequests` aceptan `state: opened` y **`groupId`**, que incluye los subgrupos. Así el mismo documento sirve para los dos ámbitos:

| Ámbito | Variable `gid` |
|---|---|
| Grupo (`networking`, incluidos sus subgrupos) | el global ID del grupo |
| Espacio personal | `null`, y se filtran en el cliente los proyectos que no son del usuario |

`groupId` es un global ID, no una ruta, pero no cuesta una consulta extra: la lista de ámbitos ya devuelve `id` y `fullPath` juntos (`currentUser { groups { nodes { id fullPath } } }`), así que el ID viaja con el ámbito elegido. Solo hace falta resolver `group(fullPath:) { id }` cuando el usuario escribe la ruta a mano.

- *Alternativa descartada*: `group(fullPath:) { mergeRequests(includeSubgroups: true, authorUsername: …) }`. También existe en la instancia y evita el global ID, pero obliga a dos formas de consulta distintas (grupo y personal) y a filtrar por nombre de usuario en vez de por relación directa. Queda documentada como recambio si algún día aparece una instancia donde `groupId` no exista.

### 5. Traducción al modelo neutro

Todos los campos de esta tabla están comprobados contra GitLab CE 19.2.7.

| Campo neutro | Origen en GitLab |
|---|---|
| `id` | `id` global (`gid://gitlab/MergeRequest/83164`) |
| `repo` | `project.fullPath` |
| `number` | `iid` (llega como texto, se convierte a entero) |
| `approvals` | `approvedBy.nodes[].username` |
| `changes_requested` | algún `reviewers.nodes[].mergeRequestInteraction.reviewState == REQUESTED_CHANGES` |
| `review_pending` | el usuario figura en `reviewers` y su `reviewState` es `UNREVIEWED` o `REVIEW_STARTED` |
| `checks` | `headPipeline.status`: `SUCCESS`→correcto; `FAILED`/`CANCELED`/`CANCELING`→fallido; `CREATED`/`PENDING`/`PREPARING`/`RUNNING`/`WAITING_FOR_RESOURCE`/`WAITING_FOR_CALLBACK`/`SCHEDULED`→en curso; `SKIPPED`/`MANUAL`/`headPipeline: null`→ninguno |
| `conflicts` | `conflicts`, pero si `mergeStatusEnum` es `UNCHECKED` o `CHECKING` se conserva el último valor conocido, igual que el `MERGEABLE` pendiente de GitHub |
| `unresolved` | `resolvableDiscussionsCount - resolvedDiscussionsCount` |
| `draft` | `draft` |
| `ready_to_merge` | no borrador, sin conflictos, checks correcto o ninguno, nadie pidió cambios y aprobado |
| `state` | `state` en minúsculas: `merged`, `closed`, `opened`; `locked` cuenta como abierto |

Dos matices que salieron de los datos reales:

- **Aprobado** se resuelve como `approved or len(approvals) > 0`, el mismo repliegue que ya hace el proveedor de GitHub con `reviewDecision`. En un proyecto de CE sin reglas de aprobación, `approved` no se vuelve cierto solo porque no haya nada que exigir; la lista de aprobadores es la señal fiable de que alguien aprobó.
- **`detailedMergeStatus` no sirve para "listo para fusionar"**: un MR sin ninguna aprobación aparece como `MERGEABLE`, porque en CE no hay regla de aprobación que lo bloquee. Dejaría pasar como listos MR que nadie ha revisado, al revés de lo que hace el proveedor de GitHub.

La caché `known_conflicts` del proveedor de GitHub se repite aquí por la misma razón: GitLab calcula la fusionabilidad de forma asíncrona y oscilaría entre "con conflictos" y "sin saberlo" en ciclos consecutivos.

### 5b. Presupuesto de complejidad: 50 por página y campos justos

El límite es 250 por petición autenticada (`queryComplexity { score limit }` lo dice en la misma respuesta). Medido contra la instancia, con las tres conexiones:

| Documento | Score |
|---|---|
| Campos completos, `first: 100` | 226 |
| **Campos justos, `first: 50`** | **169** |
| Campos justos, `first: 25` | 142 |
| Solo escalares, `first: 50` | 88 |

El primer borrador del documento marcaba 242 de 250 porque arrastraba campos que el modelo neutro no usa (`detailedMergeStatus`, `mergeable`, `mergeableDiscussionsState`, `assignees`, `userNotesCount`). Quitarlos devuelve 73 puntos.

Decisión: **50 nodos por página**, igual que el proveedor de GitHub, con 81 puntos de margen. El campo más caro es `reviewers` anidado (+39), y su coste no depende de cuántos revisores se pidan, así que no se gana nada limitándolo. Si algún día hace falta más margen, lo barato es bajar la página antes que recortar campos: de 50 a 25 ahorra 27 puntos.

El proveedor pide `queryComplexity { score limit }` en el propio documento de sondeo y registra el score cuando pase del 80 % del límite, para que un cambio de campos que acerque al techo se vea en el registro antes de romper en producción.

### 6. La clave de almacenamiento la declara el proveedor

Se añade al contrato `instance_key: str`:

- `GitHubProvider` → `"github"`. **No cambia nada de lo ya guardado**: ni la entrada del keyring ni `state-github.json`. Sin migración, sin riesgo.
- `GitLabProvider` → `"gitlab@<slug>"`, donde el slug sale del host normalizado con todo lo que no sea alfanumérico convertido en `-` (`https://gitlab.empresa.com:8443/git` → `gitlab-empresa-com-8443-git`). Así el nombre vale como entrada del keyring y como nombre de archivo en Windows y en Linux.

`CredentialStore` y `state_store.path_for` pasan a recibir esa clave en lugar del nombre del proveedor.

- *Alternativa descartada*: clave uniforme `proveedor@host` para todos, con migración de lo guardado por GitHub. Más coherente sobre el papel, pero obliga a escribir y probar una migración de keyring para no ganar nada observable.

### 7. El cambio de forja en caliente se concentra en un `rebind`

`App.__init__` extrae un método —`_bind_forge()`— que, a partir de `self.cfg`, construye proveedor, `CredentialStore`, token, ruta de estado y estado, y se lo entrega al sondeo. `settings_save` lo vuelve a llamar cuando cambian `provider` o el host, dentro del mismo bloqueo que ya protege la configuración:

1. `poller.save_now()` persiste el estado de la forja que se abandona.
2. Se construye todo lo nuevo.
3. `Poller.rebind(provider, settings, state, state_path)` sustituye proveedor, ajustes, estado y ruta, y reinicia lo derivado: `login`, `last_success`, `suspended_until`, `error`, `health`.
4. Se limpian las novedades y lo pendiente de notificar (`Inbox`, `Notifier.reset()`), para que el primer sondeo de la forja nueva no sea un aluvión de notificaciones ni deje el contador con lo de la anterior.
5. `_refresh_ui()` redibuja panel, tooltip e icono.

El hilo de sondeo no se reinicia: `rebind` toma el mismo `_settings_lock` que `reconfigure` y el ciclo siguiente ya trabaja con lo nuevo. Un sondeo en vuelo al momento del cambio se descarta al terminar comparando una marca de generación, para que no escriba el resultado de la forja vieja sobre el estado de la nueva.

- *Alternativa descartada*: pedir reinicio al cambiar de proveedor. Es menos trabajo, pero rompe la promesa que ya cumple la ventana ("guardar aplica sin reiniciar") justo en el ajuste más visible.

### 8. Los textos de la credencial los describe el proveedor

El contrato gana un descriptor —nombre visible, etiqueta y marcador del ámbito, permisos a pedir, URL de creación del token y si admite host configurable—. `settings_model.load` deja de importar `providers.github` y lo arma desde el proveedor activo, más la lista de proveedores disponibles para el desplegable. `settings.html` pierde "Crear token en GitHub", "fine-grained", "Organización" y "PR" de sus textos fijos.

Con eso, `App.open_url` deja de tener el caso especial `settings_model.github.CREATE_TOKEN_URL`: la URL de creación pertenece al host del proveedor activo y `allows_url` ya la cubre.

### 9. Normalización y validación del host en `config.py`

`[gitlab] host` se normaliza al cargar: se recortan espacios y la barra final, y si no trae esquema se asume `https://`. Un host que no sea texto, o con un esquema distinto de `http`/`https`, deja un aviso y el proveedor no se construye: la aplicación queda en "sin configurar" en vez de lanzar peticiones a una dirección sin sentido. Las dos tablas `[github]` y `[gitlab]` se conservan siempre en el archivo, de modo que ir y volver entre forjas no obliga a reescribir el ámbito.

### 10. `PR_WATCH_TOKEN` se indexa por instancia

La variable de entorno y el `.env` de desarrollo ganan hoy al keyring, y no distinguen forja: con el cambio en caliente, un token de `gitlab.com` se usaría contra la instancia propia y fallaría con un error confuso. El orden de lectura pasa a buscar primero `PR_WATCH_TOKEN_<CLAVE>` (por ejemplo `PR_WATCH_TOKEN_GITLAB_GITLAB_TELCONET_EC`) y a caer en `PR_WATCH_TOKEN` si no está.

Es una línea en `credential.py`, deja intacto el flujo de desarrollo con una sola forja, y deja de mentir cuando hay dos.

- *Alternativa descartada*: ignorar la variable al cambiar de forja en caliente. Menos código, pero el comportamiento depende de cómo llegaste a esa forja, que es justo lo que desconcierta al depurar.

## Risks / Trade-offs

- **La introspección del esquema miente** → devuelve un esquema cacheado que incluye campos que la instancia rechaza al ejecutar. Las fixtures de prueba se capturan de respuestas de consultas reales, nunca de la introspección.
- **Edición CE frente a EE** → el documento solo usa campos de CE, que también existen en EE. `metadata { enterprise }` queda registrado al verificar, para que un informe de fallo diga de qué edición viene.
- **El presupuesto de complejidad se consume solo** → 169 de 250 con los campos actuales; cualquier campo nuevo lo acerca al techo. El sondeo registra el score cuando supera el 80 %, y hay una prueba que falla si el documento crece más de lo previsto.
- **No hay cabeceras de límite en las respuestas normales** → comprobado: `RateLimit-*` no viene salvo cuando se agota. El camino "429 sin cabecera → margen por defecto" no es el raro, es el habitual en esta instancia.
- **El ámbito personal trae merge requests de más y filtra en el cliente** → es el único ámbito sin filtro en el servidor; coste acotado por el tope de páginas.
- **El cambio en caliente toca el hilo de sondeo** → la marca de generación evita que un sondeo en vuelo contamine la forja nueva; es la parte con más riesgo de regresión y la que más cubre la batería de pruebas de `App`.
- **GitLab self-hosted detrás de un certificado de CA corporativa** → `truststore` ya usa el almacén del sistema; comprobado que `gitlab.telconet.ec` valida sin configuración extra. El fallo de validación se traduce a un mensaje que dice qué hacer en lugar de un error de SSL crudo.
- **Más superficie en la ventana de ajustes** → el selector de proveedor y el campo de host se validan en el modelo (`settings_model`), que se prueba sin interfaz, como ya ocurre con el resto.

## Migration Plan

No hay migración de datos: la clave de GitHub no cambia y `[gitlab]` es una tabla nueva con valores por defecto. Un `config.toml` escrito por la versión anterior se sigue leyendo tal cual.

Marcha atrás: el proveedor nuevo vive en su propio módulo y la única forma de activarlo es la clave `provider`; volver a `github` —desde Ajustes o editando el archivo— devuelve la aplicación a su comportamiento anterior, con su token y su estado intactos.

## Open Questions

Las dos preguntas con las que nació este diseño —los nombres de los campos y el tamaño de página— quedaron cerradas contra `gitlab.telconet.ec` (CE 19.2.7): la tabla de traducción está verificada campo por campo y la página son 50 nodos, con 81 puntos de margen de complejidad. Queda lo que no se puede comprobar desde aquí:

- **Cuándo se vuelve cierto `approved` en CE.** El único MR de prueba no tenía aprobaciones, así que no se distingue "requiere una aprobación" de "requiere cero". El repliegue `approved or len(approvals) > 0` da el resultado correcto en ambos casos, pero conviene confirmarlo con un MR aprobado de verdad al implementar.
- **Instancias anteriores a la 19.** El mínimo declarado es 16 por documentación, no por prueba: no hay ninguna instancia vieja a mano. Si aparece una, lo que fallará primero es `groupId` en las conexiones de `currentUser`, y el recambio ya está identificado en la decisión 4.
- **`gitlab.com`.** No se probó. Es más nueva que 19.2 y además EE, así que todo lo que funciona en CE 19.2 debería funcionar allí; la primera conexión real lo confirmará.
