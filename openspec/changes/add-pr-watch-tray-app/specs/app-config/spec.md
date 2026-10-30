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

La configuración SHALL exponer al menos: el proveedor de forja, la organización de GitHub, el intervalo de sondeo, el tope de pull requests por bloque, los minutos que un pull request fusionado o cerrado permanece visible, y si las notificaciones están activadas.

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

### Requirement: Autoarranque con el sistema

La aplicación SHALL registrarse para arrancar con la sesión del usuario en su primera ejecución, sin preguntar.

#### Scenario: Registro en Windows
- **WHEN** la aplicación corre por primera vez en Windows
- **THEN** añade una entrada con la orden que la arranca bajo la clave `Run` del usuario actual en el registro

#### Scenario: Registro en Linux
- **WHEN** la aplicación corre por primera vez en Linux
- **THEN** escribe un archivo `.desktop` en `~/.config/autostart/`

#### Scenario: Registro idempotente
- **WHEN** la aplicación arranca y ya está registrada para el autoarranque
- **THEN** no duplica la entrada ni la reescribe innecesariamente

#### Scenario: La aplicación cambió de sitio
- **WHEN** la aplicación arranca desde una ruta distinta a la registrada
- **THEN** actualiza la entrada de autoarranque para que apunte a la ruta actual

#### Scenario: Ejecución desde el código en desarrollo
- **WHEN** la aplicación corre desde el código fuente y no empaquetada
- **THEN** no se registra para el autoarranque, para no dejar apuntando la sesión del desarrollador a un intérprete y un directorio de trabajo

#### Scenario: Registro imposible
- **WHEN** el registro de autoarranque falla por permisos o porque el entorno no lo soporta
- **THEN** la aplicación avisa una vez y sigue funcionando con normalidad

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
