## Why

Hoy pr-watch solo habla con `github.com`: el único proveedor implementado es `github` y el host está escrito a fuego en el código. Quien trabaja contra GitLab —la nube pública o una instancia propia de la empresa— no puede usar la aplicación, aunque la arquitectura ya se diseñó para esto: el modelo neutro de `forge-provider`, el registro de proveedores y el estado persistido por proveedor ya existen y no se han estrenado nunca con un segundo proveedor.

Falta lo que este cambio aporta: el proveedor de GitLab, un host configurable (que es lo único que separa la nube de una instancia propia) y la posibilidad de cambiar de forja desde Ajustes sin editar archivos a mano.

## What Changes

- **Proveedor `gitlab` nuevo**, de solo lectura, contra la API GraphQL de la instancia (`<host>/api/graphql`). Cubre a la vez GitLab cloud y self-hosted: la única diferencia entre ambos es el host configurado. Versión mínima soportada: GitLab 16.
- **Host configurable**: `[gitlab] host` en `config.toml`, con `https://gitlab.com` por defecto. El host decide la URL de la API, la URL web, el enlace para crear el token y las URL que la aplicación acepta abrir en el navegador.
- **El ámbito en GitLab es un grupo o el espacio de nombres personal**: admite rutas con subgrupos (`empresa/plataforma/red`), que el validador de GitHub rechazaría.
- **Vocabulario propio**: "MR", prefijo `!` y el host como etiqueta. El panel, el tooltip y las notificaciones ya leen el vocabulario del proveedor; no cambian.
- **Cada proveedor declara la clave con la que se guardan su credencial y su estado**. GitLab la compone con la instancia (`gitlab@gitlab.com` frente a `gitlab@gitlab.empresa.com`), para que alternar entre la nube y la instancia propia no pise la credencial ni mezcle el estado de la otra. GitHub, que solo sirve a `github.com`, conserva su clave actual: lo ya guardado sigue sirviendo y no hace falta migrar nada.
- **Selector en la ventana de Ajustes**: desplegable de proveedor (GitHub / GitLab) y, para GitLab, campo de host. Cambiar de proveedor y guardar aplica en caliente —credencial, ámbitos, vocabulario, estado y sondeo— sin reiniciar la aplicación, igual que ya ocurre al cambiar el token.
- **Los textos de Ajustes dejan de nombrar GitHub**: los permisos del token, el enlace de creación, la etiqueta del ámbito y el texto de ayuda los aporta el proveedor activo.
- La `[github]` existente y su comportamiento **no cambian**; GitHub sigue siendo el proveedor por defecto.

### Fuera de alcance

- Ver PRs de GitHub y MRs de GitLab a la vez en el mismo panel: sigue habiendo **un proveedor activo**.
- Desactivar la verificación TLS o configurar una CA propia desde la aplicación: una instancia self-hosted con certificado de una CA corporativa funciona si esa CA está en el almacén del sistema, como ya ocurre con un proxy que intercepta TLS.
- Soporte de instancias anteriores a GitLab 16, Bitbucket, Gitea o Azure DevOps.

## Capabilities

### New Capabilities
- `gitlab-client`: el proveedor de GitLab (cloud y self-hosted) de solo lectura — autenticación, host configurable, consulta de merge requests por relación, traducción al modelo neutro, versión mínima de la instancia, límites y errores clasificados.

### Modified Capabilities
- `forge-provider`: `gitlab` pasa a ser un valor implementado de `provider`; la identidad del proveedor activo incluye el host de la instancia; el cambio de proveedor ocurre en caliente, no al reiniciar.
- `app-config`: tabla `[gitlab]` con `host`, `group` y `user`, con sus reglas de validación y corrección.
- `credential-storage`: la entrada del keyring y el archivo de respaldo se identifican por proveedor **e instancia**, con migración de las claves antiguas.
- `settings-window`: selector de proveedor y de host, textos de la credencial aportados por el proveedor, y qué pasa con lo verificado al cambiar de proveedor o de host.

## Impact

- **Código nuevo**: `pr_watch/providers/gitlab.py` (proveedor GraphQL) y sus pruebas con fixtures en `tests/fixtures/gitlab/`.
- **Código modificado**:
  - `pr_watch/providers/__init__.py`: registro con la entrada `gitlab`; creación del proveedor a partir de la configuración (necesita el host, hoy `create(name)` no recibe nada más).
  - `pr_watch/providers/base.py`: el contrato gana la clave de instancia que usan credencial y estado.
  - `pr_watch/config.py`: `GitLabSettings`, validación del host y `scope()` / `with_scope()` por proveedor.
  - `pr_watch/credential.py` y `pr_watch/state_store.py`: la clave la declara el proveedor, en lugar de ser siempre su nombre.
  - `pr_watch/app.py`: recrear proveedor, credencial, estado y sondeo al guardar un cambio de proveedor o de host; `open_url` deja de comparar contra una constante de GitHub.
  - `pr_watch/settings_model.py`: los datos de la ventana salen del proveedor activo, no de `providers.github`.
  - `pr_watch/ui/settings.html` y `settings.js`: selector de proveedor, campo de host y textos variables.
  - `README.md`: configuración de GitLab y permisos del token.
- **Dependencias**: ninguna nueva. Se reutiliza el transporte `requests` + `truststore` del proveedor de GitHub.
- **Riesgo principal**: la disponibilidad de campos GraphQL varía entre versiones de GitLab; la verificación comprueba la versión de la instancia y lo dice claro en lugar de fallar con un error críptico de GraphQL.
