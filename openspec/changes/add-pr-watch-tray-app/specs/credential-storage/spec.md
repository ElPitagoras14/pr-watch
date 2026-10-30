## Purpose

Define dónde y cómo se guarda el token de acceso de la forja, cuándo se pide, cómo se borra y las garantías de que nunca se expone.

## ADDED Requirements

### Requirement: El token vive en el keyring del sistema

El token de acceso SHALL guardarse en el almacén de credenciales del sistema operativo bajo el servicio `pr-watch`: el Administrador de credenciales en Windows y el Secret Service en Linux. El nombre de la entrada SHALL identificar al proveedor, para que un segundo proveedor pueda tener su propio token sin pisar el primero.

#### Scenario: Guardado en Windows
- **WHEN** la aplicación guarda el token en Windows
- **THEN** queda en el Administrador de credenciales bajo el servicio `pr-watch`

#### Scenario: Lectura al arrancar
- **WHEN** la aplicación arranca y existe un token guardado para el proveedor configurado
- **THEN** lo recupera del keyring sin pedir nada al usuario

### Requirement: Respaldo a archivo cuando no hay keyring

Cuando el sistema no ofrezca un almacén de credenciales, la aplicación SHALL guardar el token en un archivo legible solo por el usuario (permisos `600` en Linux) dentro de su directorio de configuración, y SHALL avisar de que el token quedó en texto plano.

#### Scenario: Linux sin Secret Service
- **WHEN** la aplicación corre en Linux sin Secret Service disponible
- **THEN** guarda el token en un archivo con permisos `600` en el directorio de configuración

#### Scenario: Aviso de texto plano
- **WHEN** el token se guarda en el archivo de respaldo
- **THEN** la aplicación avisa explícitamente de que el token quedó en texto plano, y el aviso queda visible en la ventana de ajustes

#### Scenario: Preferencia por el keyring
- **WHEN** existe un token en el archivo de respaldo y el keyring pasa a estar disponible
- **THEN** la aplicación usa el keyring y deja de depender del archivo

### Requirement: El token nunca se expone

El token MUST NOT aparecer en logs, en mensajes de error, en el tooltip, en el menú, en el panel, en la query string de ninguna petición ni en ningún dato que se entregue a la interfaz web.

#### Scenario: Error de autenticación
- **WHEN** GitHub rechaza el token y la aplicación registra el fallo
- **THEN** el registro describe el fallo sin incluir el token ni ningún fragmento suyo

#### Scenario: Token en configuración
- **WHEN** el usuario abre `config.toml`
- **THEN** no encuentra el token allí

#### Scenario: El panel nunca recibe el token
- **WHEN** la aplicación entrega datos al panel o a la ventana de ajustes
- **THEN** esos datos no contienen el token guardado; como mucho indican si existe uno

### Requirement: Origen del token durante el desarrollo

La aplicación SHALL aceptar el token desde la variable de entorno `PR_WATCH_TOKEN` o desde un archivo `.env` del directorio de trabajo, y SHALL dar prioridad a esa fuente sobre el keyring.

#### Scenario: Token desde el entorno
- **WHEN** la variable `PR_WATCH_TOKEN` está definida al arrancar
- **THEN** la aplicación la usa y no consulta el keyring

#### Scenario: Otras variables no se leen
- **WHEN** está definida `GITHUB_TOKEN` o `GH_TOKEN` pero no `PR_WATCH_TOKEN`
- **THEN** la aplicación las ignora, porque suelen llevar permisos de escritura que esta herramienta no debe tener

#### Scenario: Sin token en ninguna fuente
- **WHEN** no hay token ni en el entorno ni en el keyring ni en el archivo de respaldo
- **THEN** la aplicación arranca, no sondea, y el tooltip indica que falta configurarla, sin caerse

#### Scenario: El archivo de pruebas no entra al repositorio
- **WHEN** existe un archivo `.env` en el directorio del proyecto
- **THEN** está excluido del control de versiones

### Requirement: Configuración al abrir por primera vez

Cuando no haya token en ninguna fuente, la aplicación SHALL pedir la organización y el token en su ventana de ajustes, que aparece la primera vez que el usuario abre el panel. La aplicación MUST NOT abrir ninguna ventana por su cuenta al arrancar, MUST NOT recurrir a diálogos del sistema operativo y MUST NOT guardar la credencial sin haberla verificado antes contra GitHub.

#### Scenario: Primera ejecución sin token
- **WHEN** la aplicación arranca sin token en ninguna fuente
- **THEN** queda en la bandeja indicando en el tooltip que falta configurarla, sin abrir ninguna ventana y sin diálogos del sistema

#### Scenario: El usuario abre el panel sin token
- **WHEN** el usuario abre el panel por primera vez y no hay token guardado
- **THEN** se abre con él la ventana de ajustes, con la organización configurada ya rellena si la hay

#### Scenario: Lo introducido se guarda tras verificarse
- **WHEN** el usuario introduce una organización y un token que superan la verificación
- **THEN** la organización se guarda en `config.toml`, el token en el almacén de credenciales, y la aplicación empieza a sondear sin reiniciarse

#### Scenario: Arranques posteriores
- **WHEN** la aplicación arranca y ya hay un token guardado
- **THEN** no pide nada y no abre ninguna ventana

#### Scenario: El token sigue sin aparecer en claro
- **WHEN** la ventana de ajustes maneja el token
- **THEN** se muestra enmascarado y no se escribe en `config.toml` ni en ningún registro

### Requirement: El usuario puede borrar la credencial guardada

La aplicación SHALL ofrecer una forma de borrar explícitamente el token guardado, tanto del keyring como del archivo de respaldo si existiera. Borrar la credencial MUST NOT tocar `config.toml` ni la organización configurada.

#### Scenario: Borrado del keyring
- **WHEN** el usuario pide borrar la credencial y el token estaba en el keyring
- **THEN** la aplicación lo elimina de ahí

#### Scenario: Borrado del archivo de respaldo
- **WHEN** el usuario pide borrar la credencial y existe un archivo de respaldo
- **THEN** la aplicación también elimina ese archivo

#### Scenario: Nada que borrar no es un error
- **WHEN** el usuario pide borrar la credencial y no había ninguna guardada
- **THEN** la aplicación lo trata como un borrado exitoso, sin avisar de ningún fallo

#### Scenario: La organización se conserva
- **WHEN** el usuario borra la credencial
- **THEN** la organización configurada en `config.toml` no cambia
