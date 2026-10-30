## MODIFIED Requirements

### Requirement: Selección del proveedor por configuración

El proveedor activo SHALL elegirse con la clave `provider` de `config.toml`. Los valores implementados SHALL ser `github` y `gitlab`. El usuario SHALL poder cambiar de proveedor desde la ventana de ajustes, sin editar el archivo a mano.

#### Scenario: Proveedor por defecto
- **WHEN** `config.toml` no declara proveedor
- **THEN** la aplicación usa `github`

#### Scenario: Cambio de proveedor
- **WHEN** el usuario cambia el proveedor y guarda
- **THEN** la aplicación pasa a usar el nuevo proveedor con su propia credencial, su propio ámbito y su propio vocabulario, y el estado persistido del anterior no se mezcla con el del nuevo

#### Scenario: Cambio de proveedor sin reiniciar
- **WHEN** el usuario guarda un cambio de proveedor con la aplicación en marcha
- **THEN** el sondeo, el panel, la bandeja y las notificaciones pasan al proveedor nuevo sin reiniciar la aplicación, y el panel deja de mostrar lo que venía del anterior

## ADDED Requirements

### Requirement: La instancia forma parte de la identidad del proveedor

Cada proveedor SHALL declarar la clave con la que se guardan su credencial y su estado persistido. Cuando un proveedor pueda apuntar a varias instancias —GitLab cloud y una o varias instancias propias—, esa clave SHALL incluir la instancia; cuando solo sirva a una, SHALL seguir siendo el nombre del proveedor, para no invalidar lo ya guardado. Cambiar de instancia MUST NOT pisar la credencial de la otra ni mezclar sus pull requests, sus novedades ni sus elementos ya vistos.

#### Scenario: Dos instancias de GitLab
- **WHEN** el usuario alterna entre `gitlab.com` y `gitlab.empresa.com`
- **THEN** cada una conserva su propio token guardado y su propio estado, y ninguna hereda los merge requests de la otra

#### Scenario: Volver a una instancia ya usada
- **WHEN** el usuario vuelve a una instancia que ya había configurado antes
- **THEN** la aplicación recupera su token y su estado, y no vuelve a pedir la credencial

#### Scenario: Lo ya guardado sigue sirviendo
- **WHEN** la aplicación arranca con la credencial y el estado de GitHub guardados antes de este cambio
- **THEN** los encuentra donde estaban, porque la clave de un proveedor de instancia única no cambia, y no se pide nada al usuario

#### Scenario: Instancia sin estado previo
- **WHEN** el usuario configura una instancia por primera vez
- **THEN** la aplicación arranca para ella como la primera vez, sin novedades falsas por elementos que nunca vio
