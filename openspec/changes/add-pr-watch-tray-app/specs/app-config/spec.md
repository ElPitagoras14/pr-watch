## Purpose

Define dónde vive la configuración de pr-watch, qué claves expone, cómo se corrigen los valores fuera de rango y cómo se registra la aplicación para arrancar con la sesión.

## ADDED Requirements

### Requirement: Configuración en archivo TOML

La configuración SHALL vivir en `config.toml` dentro del directorio de configuración del usuario, bajo el identificador `pr-watch`: `%APPDATA%\pr-watch` en Windows y `~/.config/pr-watch` en Linux.

#### Scenario: Primera ejecución sin configuración
- **WHEN** la aplicación arranca y no existe `config.toml`
- **THEN** lo crea con los valores por defecto y continúa

#### Scenario: Configuración ilegible
- **WHEN** `config.toml` existe pero no es TOML válido
- **THEN** la aplicación arranca con los valores por defecto, conserva el archivo original sin sobrescribirlo y avisa del problema

#### Scenario: Clave desconocida
- **WHEN** `config.toml` contiene una clave que la aplicación no reconoce
- **THEN** la ignora y arranca normalmente, en lugar de abortar

### Requirement: Claves configurables

La configuración SHALL exponer al menos: el proveedor de forja, la organización de GitHub o en su lugar la cuenta personal (`[github] org` o `[github] user`; si vienen las dos, gana la organización y se avisa), el intervalo de sondeo, el tope de pull requests por bloque, los minutos que un pull request fusionado o cerrado permanece visible, y si las notificaciones están activadas.

Los ajustes propios de cada proveedor SHALL vivir en una tabla con el nombre del proveedor (por ejemplo `[github]`), para que añadir otro proveedor no obligue a renombrar ni mezclar claves.

El tope SHALL llamarse `max_per_block` y SHALL aplicarse a CADA bloque por separado, no a la suma de los dos.

#### Scenario: Valores por defecto
- **WHEN** la aplicación arranca con la configuración recién creada
- **THEN** usa `github` como proveedor, ninguna organización, 60 segundos de intervalo, 5 pull requests por bloque, 15 minutos de caducidad y las notificaciones apagadas

#### Scenario: Intervalo fuera de rango
- **WHEN** la configuración declara un intervalo de sondeo menor a 30 segundos
- **THEN** la aplicación lo eleva a 30 segundos y avisa, para no consumir el límite de peticiones de GitHub

#### Scenario: Tope fuera de rango
- **WHEN** la configuración declara un tope por bloque menor que 1 o mayor que 20
- **THEN** la aplicación lo ajusta al extremo más cercano y avisa, porque un tope de cero dejaría la lista vacía y uno demasiado alto desbordaría un panel sin desplazamiento

#### Scenario: Proveedor desconocido
- **WHEN** la configuración declara un proveedor que la aplicación no implementa
- **THEN** la aplicación arranca sin sondear, el tooltip y el panel indican que el proveedor no está soportado, y el archivo no se modifica

### Requirement: Autoarranque con el sistema, a elección del usuario

La aplicación SHALL arrancar con la sesión del usuario solo si el usuario lo activa, desde la entrada `Arrancar con la sesión` del menú de bandeja. El autoarranque SHALL venir desactivado: la aplicación MUST NOT registrarse por su cuenta. La propia entrada del sistema (la clave `Run` en Windows, el `.desktop` en Linux) SHALL ser la única fuente de verdad de si está activado; no se guarda aparte en `config.toml`.

#### Scenario: Primera ejecución
- **WHEN** la aplicación corre por primera vez
- **THEN** no crea ninguna entrada de autoarranque, y la entrada del menú aparece desmarcada

#### Scenario: Activar en Windows
- **WHEN** el usuario activa `Arrancar con la sesión` en Windows
- **THEN** se añade una entrada con la ruta del ejecutable bajo la clave `Run` del usuario actual, y la entrada del menú aparece marcada

#### Scenario: Activar en Linux
- **WHEN** el usuario activa `Arrancar con la sesión` en Linux
- **THEN** se escribe un archivo `.desktop` en `~/.config/autostart/` que apunta al binario

#### Scenario: Desactivar
- **WHEN** el usuario desactiva `Arrancar con la sesión`
- **THEN** se borra la entrada del sistema y la aplicación deja de arrancar con la sesión

#### Scenario: El estado lo dice el sistema
- **WHEN** el usuario borra la entrada a mano con las herramientas del sistema
- **THEN** la entrada del menú aparece desmarcada la próxima vez que se abre el menú

#### Scenario: La aplicación cambió de sitio
- **WHEN** el autoarranque está activado y la aplicación arranca desde una ruta distinta a la registrada
- **THEN** actualiza la entrada para que apunte a la ruta actual, sin duplicarla

#### Scenario: Ejecución desde el código en desarrollo
- **WHEN** la aplicación corre desde el código fuente y no empaquetada
- **THEN** la entrada del menú aparece inhabilitada, para no dejar la sesión del desarrollador apuntando a un intérprete y un directorio de trabajo

#### Scenario: Activación imposible
- **WHEN** activar o desactivar el autoarranque falla por permisos o porque el entorno no lo soporta
- **THEN** la aplicación lo registra, la entrada del menú refleja el estado real y la aplicación sigue funcionando con normalidad

### Requirement: Acceso a la configuración desde la ventana de ajustes

La aplicación SHALL dar acceso a sus preferencias desde la ventana de ajustes: la organización y el token, el intervalo de sondeo, las notificaciones y el tope por bloque. El menú de bandeja MUST NOT duplicar esas preferencias; su papel es dar acceso al panel.

#### Scenario: Cambiar una preferencia
- **WHEN** el usuario cambia el intervalo, las notificaciones o el tope por bloque en la ventana de ajustes y guarda
- **THEN** el cambio se escribe en `config.toml` y surte efecto sin reiniciar la aplicación

#### Scenario: Cambiar la organización o el token
- **WHEN** el usuario quiere apuntar a otra organización o renovar el token
- **THEN** lo hace en la ventana de ajustes, que lo verifica contra GitHub antes de guardarlo

#### Scenario: Ajustes que no están en la ventana
- **WHEN** el usuario quiere cambiar un ajuste sin control propio, como la caducidad de los fusionados
- **THEN** la ventana de ajustes ofrece abrir `config.toml` en el editor predeterminado del sistema
