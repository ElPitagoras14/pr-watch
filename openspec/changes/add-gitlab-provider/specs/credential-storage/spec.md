## MODIFIED Requirements

### Requirement: El token vive en el keyring del sistema

El token de acceso SHALL guardarse en el almacén de credenciales del sistema operativo bajo el servicio `pr-watch`: el Administrador de credenciales en Windows y el Secret Service en Linux. El nombre de la entrada SHALL ser la clave que declara el proveedor, que identifica al proveedor y, cuando sirva a varias instancias, también a la instancia; así un segundo proveedor —o la misma forja en otra instancia— tiene su propio token sin pisar el primero.

#### Scenario: Guardado en Windows
- **WHEN** la aplicación guarda el token en Windows
- **THEN** queda en el Administrador de credenciales bajo el servicio `pr-watch`

#### Scenario: Lectura al arrancar
- **WHEN** la aplicación arranca y existe un token guardado para el proveedor y la instancia configurados
- **THEN** lo recupera del keyring sin pedir nada al usuario

#### Scenario: Un token por instancia
- **WHEN** el usuario tiene configurados `gitlab.com` y `gitlab.empresa.com` en momentos distintos
- **THEN** cada instancia tiene su propia entrada en el almacén, y guardar una MUST NOT sobrescribir la otra

#### Scenario: El token de GitHub sigue donde estaba
- **WHEN** la aplicación arranca tras este cambio con un token de GitHub ya guardado
- **THEN** lo encuentra con la misma entrada de antes, porque la clave de un proveedor de instancia única no cambia

### Requirement: Respaldo a archivo cuando no hay keyring

Cuando el sistema no ofrezca un almacén de credenciales, la aplicación SHALL guardar el token en un archivo legible solo por el usuario (permisos `600` en Linux) dentro de su directorio de configuración, y SHALL avisar de que el token quedó en texto plano. El nombre del archivo SHALL identificar al proveedor y a la instancia, igual que la entrada del keyring.

#### Scenario: Linux sin Secret Service
- **WHEN** la aplicación corre en Linux sin Secret Service disponible
- **THEN** guarda el token en un archivo con permisos `600` en el directorio de configuración

#### Scenario: Aviso de texto plano
- **WHEN** el token se guarda en el archivo de respaldo
- **THEN** la aplicación avisa explícitamente de que el token quedó en texto plano, y el aviso queda visible en la ventana de ajustes

#### Scenario: Preferencia por el keyring
- **WHEN** existe un token en el archivo de respaldo y el keyring pasa a estar disponible
- **THEN** la aplicación usa el keyring y deja de depender del archivo

#### Scenario: Un archivo por instancia
- **WHEN** no hay keyring y el usuario configura dos instancias distintas
- **THEN** cada una guarda su token en su propio archivo, sin pisarse

### Requirement: Origen del token durante el desarrollo

La aplicación SHALL aceptar el token desde una variable de entorno o desde un archivo `.env` del directorio de trabajo, y SHALL dar prioridad a esa fuente sobre el keyring. Como esa fuente no distingue forjas, la aplicación SHALL buscar primero una variable con la clave del proveedor activo (`PR_WATCH_TOKEN_<CLAVE>`) y solo después la genérica `PR_WATCH_TOKEN`.

#### Scenario: Token desde el entorno
- **WHEN** la variable `PR_WATCH_TOKEN` está definida al arrancar y no hay ninguna específica
- **THEN** la aplicación la usa y no consulta el keyring

#### Scenario: Una variable por forja
- **WHEN** el usuario alterna entre dos instancias y define una variable específica para cada una
- **THEN** cada forja usa la suya, y ninguna recibe el token de la otra

#### Scenario: La específica gana a la genérica
- **WHEN** están definidas la variable específica de la forja activa y la genérica
- **THEN** se usa la específica

#### Scenario: Otras variables no se leen
- **WHEN** está definida `GITHUB_TOKEN` o `GH_TOKEN` pero ninguna de las de la aplicación
- **THEN** la aplicación las ignora, porque suelen llevar permisos de escritura que esta herramienta no debe tener

#### Scenario: Sin token en ninguna fuente
- **WHEN** no hay token ni en el entorno ni en el keyring ni en el archivo de respaldo
- **THEN** la aplicación arranca, no sondea, y el tooltip indica que falta configurarla, sin caerse

#### Scenario: El archivo de pruebas no entra al repositorio
- **WHEN** existe un archivo `.env` en el directorio del proyecto
- **THEN** está excluido del control de versiones

### Requirement: El usuario puede borrar la credencial guardada

La aplicación SHALL ofrecer una forma de borrar explícitamente el token guardado, tanto del keyring como del archivo de respaldo si existiera. Borrar la credencial SHALL afectar solo al proveedor e instancia activos y MUST NOT tocar `config.toml`, el ámbito configurado ni las credenciales de otras instancias.

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
- **THEN** el ámbito configurado en `config.toml` no cambia

#### Scenario: Las otras instancias no se tocan
- **WHEN** el usuario cierra sesión con GitLab activo y tenía también un token de GitHub guardado
- **THEN** el token de GitHub sigue guardado
