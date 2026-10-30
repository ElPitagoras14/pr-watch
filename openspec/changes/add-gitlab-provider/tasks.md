## 1. Contrato del proveedor y registro

- [x] 1.1 `providers/base.py`: añadir al `Protocol` la clave de almacenamiento (`instance_key`) y el descriptor de la ventana de ajustes (nombre visible, etiqueta y marcador del ámbito, permisos a pedir, URL de creación del token, si admite host configurable); verificar con `uv run pyright` que `GitHubProvider` sigue cumpliendo el contrato
- [x] 1.2 `providers/github.py`: implementar lo añadido — `instance_key` devuelve `"github"` (la clave de siempre, sin migración) y el descriptor traslada las constantes `TOKEN_PERMISSIONS`, `CREATE_TOKEN_URL` y la etiqueta "Cuenta u organización"; verificar con una prueba que `instance_key` no cambió respecto a la versión anterior
- [x] 1.3 `providers/__init__.py`: el registro pasa a construirse desde la configuración (`create(cfg)` en lugar de `create(name)`), con `github` y `gitlab`; verificar con pruebas que un proveedor desconocido sigue devolviendo `None` y que `create` no importa `providers` desde `config` (sin ciclo)

## 2. Configuración

- [x] 2.1 `config.py`: `GitLabSettings` con `host`, `group` y `user`; tabla `[gitlab]` en `to_dict`/`from_dict`; `scope()` y `with_scope()` por proveedor, admitiendo rutas con subgrupos; conservar siempre ambas tablas al guardar; verificar con pruebas de ida y vuelta entre proveedores que la organización de GitHub sobrevive al cambio
- [x] 2.2 `config.py`: normalización y validación del host — recorte de espacios y de la barra final, `https://` implícito, rechazo de lo que no sea texto o no use `http`/`https`, `https://gitlab.com` por defecto con aviso cuando falta; verificar con una prueba por escenario de host de `app-config`

## 3. Almacenamiento por instancia

- [x] 3.1 `credential.py`: `CredentialStore` recibe la clave del proveedor en lugar de su nombre, tanto para la entrada del keyring como para el archivo de respaldo; verificar con pruebas que dos instancias de GitLab guardan y borran tokens distintos sin pisarse y que la entrada de GitHub existente se sigue leyendo igual
- [x] 3.2 `credential.py`: el token de desarrollo se busca primero en `PR_WATCH_TOKEN_<CLAVE>` y después en `PR_WATCH_TOKEN`, tanto en el entorno como en el `.env`; verificar con pruebas que la específica gana a la genérica y que dos forjas con variable propia no se pisan
- [x] 3.3 `state_store.py`: `path_for` recibe la clave del proveedor; verificar con una prueba que `state-github.json` se sigue leyendo tal cual y que dos instancias de GitLab usan archivos distintos

## 4. Proveedor de GitLab

- [x] 4.1 `providers/gitlab.py`, esqueleto y envío: host en el constructor, URL de API y web derivadas, transporte `requests` + `truststore` reutilizado, cabecera `Authorization`, timeout y rechazo de `mutation`/`subscription` antes de enviar; `instance_key`, `vocabulary` ("MR", `!`, el host), `allows_url` contra el host configurado y `scope_label`; verificar con pruebas que un documento con `mutation` no llega al transporte y que ninguna URL fuera del host se acepta
- [x] 4.2 `providers/gitlab.py`, clasificación de errores: 401 → credencial inválida, 403/404 del ámbito → sin acceso, 429 con y sin cabecera de restablecimiento → límite agotado, 5xx y fallos de transporte → red; verificar con pruebas sobre respuestas grabadas en `tests/fixtures/gitlab/`
- [x] 4.3 `providers/gitlab.py`, versión y edición: `metadata { version enterprise }` dentro de la verificación, rechazo con la versión encontrada y la mínima si es anterior a GitLab 16, registro de versión y edición, continuación con aviso si la instancia no las informa, y traducción de un `undefinedField` a un error que nombra el campo y la versión; verificar con pruebas de los cuatro casos
- [x] 4.4 `providers/gitlab.py`, `list_scopes` y `verify`: usuario del token, espacio personal primero y grupos por ruta completa ordenados; verificación del grupo configurado y del espacio personal propio (rechazando el de otro); verificar con fixtures de token sin grupos, con subgrupos y de grupo inaccesible
- [x] 4.5 `providers/gitlab.py`, `fetch_open`: un solo documento con las tres conexiones de `currentUser` (`authoredMergeRequests`, `assignedMergeRequests`, `reviewRequestedMergeRequests`) con `state: opened` y `groupId` cuando el ámbito es un grupo —subgrupos incluidos—, 50 nodos por página, paginación por alias, deduplicación por prioridad de relación y `complete=False` cuando falla una de las tres; verificar con fixtures que incluyen un MR en dos relaciones, uno de un subgrupo y una relación con dos páginas
- [x] 4.6 `providers/gitlab.py`, ámbito personal: el mismo documento sin `groupId`, filtrando en el cliente los proyectos que no son del espacio del usuario; verificar con una fixture que incluye un MR de otro espacio y comprobar que no aparece
- [x] 4.7 `providers/gitlab.py`, traducción al modelo neutro según la tabla del diseño: aprobaciones desde `approvedBy`, cambios pedidos y revisión pendiente desde el estado de revisión de cada revisor, aprobado con el repliegue a "hay al menos un aprobador", checks desde el pipeline (incluido `headPipeline` nulo), conflictos con conservación del último valor conocido cuando el estado de fusión está sin calcular, discusiones sin resolver como resolubles menos resueltas, borrador y listo para fusionar (que NO sale del estado detallado de fusión); verificar con una prueba por regla, con fixtures capturadas de la instancia real
- [x] 4.8 `providers/gitlab.py`, presupuesto de complejidad: pedir `queryComplexity { score limit }` en el propio sondeo, registrar al superar el 80 % del límite y clasificar el rechazo por complejidad como fallo de servidor; verificar con una prueba que el documento generado no supera la puntuación medida en el diseño (169 de 250 con página de 50)
- [x] 4.9 `providers/gitlab.py`, `fetch_states` y `block_url`: estado por identificador agrupando alias de `mergeRequest(id:)` en un documento (fusionado, cerrado, inaccesible) y URL web del listado por bloque, distinta para grupo y para espacio personal; verificar con pruebas que quince identificadores no producen quince peticiones
- [ ] 4.10 `providers/gitlab.py`, modo de diagnóstico `python -m pr_watch.providers.gitlab --check` equivalente al de GitHub (resumen de lo que llega, sin mostrar el token); verificar a mano contra `gitlab.telconet.ec` (CE 19.2) y contra `gitlab.com` (EE, sin probar todavía), y ajustar la tabla de traducción si algún campo no llega

## 5. Cambio de forja en caliente

- [x] 5.1 `poller.py`: `rebind(provider, settings, state, state_path)` bajo el mismo bloqueo que `reconfigure`, reiniciando `login`, `last_success`, `suspended_until`, `error` y `health`; marca de generación para descartar el resultado de un sondeo en vuelo de la forja anterior; verificar con pruebas que usan dos proveedores falsos y un reloj inyectado, incluida la del sondeo en vuelo
- [x] 5.2 `app.py`: extraer de `__init__` un `_bind_forge()` que construya proveedor, credencial, token, estado y ruta de estado desde `self.cfg`; verificar que el arranque sigue comportándose igual con las pruebas existentes de `App`
- [x] 5.3 `app.py`: `settings_save` detecta el cambio de proveedor o de host, persiste el estado de la forja que se abandona, vuelve a atar todo, limpia novedades y notificaciones pendientes y redibuja; verificar con pruebas que tras el cambio el panel no conserva nada de la forja anterior, que no se notifica en bloque el primer sondeo y que cancelar no cambia de forja
- [x] 5.4 `app.py`: `open_url` pierde el caso especial de la URL de creación de token de GitHub y se apoya solo en el proveedor activo; verificar con pruebas que la URL de creación del proveedor activo se acepta y que una del proveedor inactivo se rechaza

## 6. Ventana de ajustes

- [x] 6.1 `settings_model.py`: `load` deja de importar `providers.github` y arma los datos desde el proveedor activo, añadiendo la lista de proveedores disponibles y el host cuando aplique; `parse` acepta proveedor y host, y `credential_changes` considera que cambiarlos invalida lo verificado; verificar con pruebas por escenario, incluida la de guardar sin token ni cambios de forja
- [x] 6.2 `ui/settings.html` y `settings.css`: selector de proveedor, campo de host visible solo donde aplica y textos de la credencial y del ámbito alimentados por el modelo, sin GitHub escrito a fuego; verificar en la vista previa que con cada proveedor cambian etiqueta del ámbito, permisos, enlace del token y el sustantivo del tope por bloque
- [x] 6.3 `ui/settings.js`: cambiar proveedor o host descarta la verificación, inhabilita el selector de ámbito y el guardado de credencial, y vuelve a verificar el token guardado de esa forja si lo hay; el ámbito a mano admite rutas con subgrupos; verificar en la vista previa cada transición y con una prueba del modelo lo que no dependa de la interfaz
- [x] 6.4 `preview.py`: escenarios de la ventana de ajustes con GitLab activo (nube e instancia propia) y con GitHub, incluido el de instancia inalcanzable y el de versión no soportada; verificar que `python -m pr_watch.preview` los dibuja

## 7. Verificación y documentación

- [x] 7.1 Repasar los deltas de `gitlab-client`, `forge-provider`, `app-config`, `credential-storage` y `settings-window` escenario por escenario y completar las pruebas que falten; verificar con `uv run python -m unittest discover -s tests` que todas pasan
- [x] 7.2 `uv run ruff check`, `uv run ruff format --check` y `uv run pyright` sin errores sobre todo el proyecto
- [ ] 7.3 Prueba a mano del recorrido completo en Windows: configurar GitHub, cambiar a GitLab cloud, cambiar a la instancia propia, volver a GitHub y comprobar que cada forja recupera su token, su ámbito y su estado sin reiniciar
- [x] 7.4 `README.md`: sección de GitLab (host de la nube y de una instancia propia, ámbito `read_api` del token, grupo o espacio personal, versión mínima y qué hacer con una CA corporativa) y actualización de la descripción del proyecto, que hoy solo habla de GitHub
