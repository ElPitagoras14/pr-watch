## Purpose

Separa la aplicación de la forja concreta: define el modelo neutro de pull request que consumen el sondeo, el panel y las notificaciones, y el contrato que cualquier proveedor (hoy GitHub; mañana GitLab cloud o self-hosted) debe cumplir.

## ADDED Requirements

### Requirement: Modelo neutro de pull request

Todo lo que no sea el proveedor —sondeo, estado persistido, novedades, panel, bandeja y notificaciones— SHALL trabajar exclusivamente con un modelo neutro de pull request. Ese modelo SHALL incluir al menos: un identificador estable y único en la forja, el repositorio, el número, el título, la URL web, el autor, el estado (abierto, fusionado, cerrado), si es borrador, la relación con el usuario, el número de aprobaciones vigentes y quiénes aprobaron, si hay cambios pedidos, el estado agregado de los checks (correcto, fallido, en curso, ninguno), si tiene conflictos, el número de conversaciones sin resolver, si está listo para fusionar, y la fecha de última actualización.

#### Scenario: Ningún concepto de la forja fuera del proveedor
- **WHEN** se añade un segundo proveedor
- **THEN** el panel, la bandeja, el sondeo y las notificaciones funcionan sin cambios, porque ninguno depende de campos o nombres propios de GitHub

#### Scenario: Vocabulario neutro en la interfaz
- **WHEN** el panel se refiere a un elemento vigilado
- **THEN** usa el vocabulario que le da el proveedor (por ejemplo "PR" y `#142` en GitHub, "MR" y `!142` en GitLab), sin que la interfaz lo tenga escrito a fuego

### Requirement: Contrato del proveedor

Un proveedor SHALL ofrecer: verificar una credencial devolviendo la identidad del usuario o un error clasificado; obtener los pull requests abiertos del usuario en sus tres relaciones; consultar el estado actual de pull requests concretos que dejaron de aparecer; y construir la URL web del listado completo de cada bloque.

Los errores SHALL clasificarse al menos en: credencial inválida, sin acceso al ámbito configurado (por ejemplo la organización), límite de peticiones agotado, y fallo de red o del servidor.

#### Scenario: Error clasificado
- **WHEN** una operación del proveedor falla
- **THEN** quien la llamó recibe una de las clases de error del contrato, no una excepción de la biblioteca HTTP ni un código de estado crudo

#### Scenario: Resultado parcial explícito
- **WHEN** alguna de las consultas de relación falla y otras no
- **THEN** el proveedor lo indica, para que el sondeo pueda negarse a purgar con datos incompletos

### Requirement: Selección del proveedor por configuración

El proveedor activo SHALL elegirse con la clave `provider` de `config.toml`. El único valor implementado en este cambio SHALL ser `github`.

#### Scenario: Proveedor por defecto
- **WHEN** `config.toml` no declara proveedor
- **THEN** la aplicación usa `github`

#### Scenario: Cambio de proveedor
- **WHEN** el usuario cambia el proveedor y reinicia
- **THEN** la aplicación usa el nuevo proveedor con su propia credencial, y el estado persistido del anterior no se mezcla con el del nuevo
