## Purpose

Proveedor de GitHub (github.com) de solo lectura: cómo se autentica, qué consulta para obtener los pull requests del usuario en una organización y cómo traduce la respuesta al modelo neutro.

## ADDED Requirements

### Requirement: Cliente de solo lectura

El cliente SHALL limitarse a leer. Contra la API GraphQL de GitHub SHALL enviar únicamente documentos de tipo `query`; el cliente MUST rechazar, antes de enviarlo, cualquier documento que contenga una `mutation` o una `subscription`. Cualquier petición REST SHALL ser `GET`.

#### Scenario: Una mutación nunca sale
- **WHEN** cualquier parte del código intenta enviar un documento GraphQL que contiene `mutation`
- **THEN** el cliente lo rechaza con un error de programación y no se emite ninguna petición

#### Scenario: El token se envía como cabecera
- **WHEN** el cliente emite una petición
- **THEN** el token viaja en la cabecera `Authorization` y nunca en la query string

### Requirement: Token de solo lectura recomendado

La aplicación SHALL indicar al usuario que cree un *fine-grained personal access token* con la organización como dueño del recurso, acceso a los repositorios que quiera vigilar, y únicamente permisos de lectura: `Pull requests`, `Metadata`, `Commit statuses` y `Checks` cuando estén disponibles para tokens de usuario.

#### Scenario: El usuario ve qué permisos dar
- **WHEN** el usuario mira la sección de la credencial en la ventana de ajustes
- **THEN** encuentra listados los permisos de lectura necesarios y un enlace a la página de GitHub para crear el token

#### Scenario: Token clásico
- **WHEN** el usuario usa un token clásico con permiso `repo`
- **THEN** la aplicación funciona igualmente, porque el propio cliente no escribe nunca

### Requirement: Verificación de la credencial

Verificar una credencial SHALL comprobar dos cosas: que GitHub acepta el token, y que con él se puede consultar la organización configurada. El resultado SHALL distinguir token inválido, organización inexistente o inaccesible, y fallo de red.

#### Scenario: Credencial válida
- **WHEN** GitHub acepta el token y la organización es accesible
- **THEN** la verificación devuelve el login del usuario

#### Scenario: Token inválido o caducado
- **WHEN** GitHub responde `401`
- **THEN** la verificación devuelve "credencial inválida" y el sondeo no se ejecuta

#### Scenario: Token sin acceso a la organización
- **WHEN** el token es válido pero la organización no existe o el token no tiene acceso a ella, por ejemplo porque la organización aún no aprobó el token
- **THEN** la verificación devuelve "sin acceso a la organización", distinto de "credencial inválida", porque lo que tiene que hacer el usuario es distinto

### Requirement: Consulta de pull requests por relación

El cliente SHALL obtener los pull requests abiertos de la organización configurada en las tres relaciones del usuario: creados por él (`author:@me`), con su revisión solicitada (`review-requested:@me`, que incluye las solicitudes a equipos suyos) y asignados a él (`assignee:@me`). Cada consulta SHALL traer en la misma respuesta los datos que necesita el modelo neutro: revisiones, checks, conflictos y conversaciones sin resolver.

#### Scenario: Las tres relaciones
- **WHEN** se ejecuta un sondeo
- **THEN** se consultan las tres relaciones y sus resultados se unifican

#### Scenario: Un pull request en dos relaciones
- **WHEN** un mismo pull request aparece en más de una relación
- **THEN** aparece una sola vez, clasificado por la relación de mayor prioridad: autor antes que revisor, y revisor antes que asignado

#### Scenario: Paginación
- **WHEN** una relación devuelve más resultados de los que caben en una página
- **THEN** el cliente recorre las páginas siguientes hasta agotar el conjunto

#### Scenario: Sin llamadas por pull request
- **WHEN** se completa un sondeo normal
- **THEN** no se emitió ninguna petición individual por pull request: todo llega en las consultas de relación

### Requirement: Traducción al modelo neutro

El cliente SHALL traducir la respuesta de GitHub al modelo neutro de `forge-provider` con estas reglas: las aprobaciones son las revisiones vigentes más recientes de cada revisor en estado aprobado; hay cambios pedidos si alguna revisión vigente los pide; los checks se resumen desde el estado agregado del último commit; hay conflictos si GitHub declara el pull request no fusionable por conflicto; las conversaciones sin resolver son los hilos de revisión no resueltos.

#### Scenario: Aprobaciones sin denominador
- **WHEN** dos revisores aprobaron un pull request
- **THEN** el modelo indica dos aprobaciones y sus logins, sin inventar un número requerido

#### Scenario: Aprobación superada
- **WHEN** un revisor aprobó y después pidió cambios
- **THEN** cuenta solo su revisión más reciente: no suma aprobación y sí marca cambios pedidos

#### Scenario: Fusionabilidad aún desconocida
- **WHEN** GitHub todavía está calculando si el pull request es fusionable
- **THEN** el modelo no marca conflictos y conserva el valor anterior conocido, en lugar de oscilar entre estados

### Requirement: Estado de pull requests que dejaron de aparecer

Cuando un pull request conocido deja de aparecer en las búsquedas de abiertos, el cliente SHALL poder consultar su estado actual por identificador para distinguir fusionado, cerrado e inaccesible.

#### Scenario: Fusionado
- **WHEN** un pull request conocido desaparece de la búsqueda y su consulta indica que se fusionó
- **THEN** el cliente lo devuelve como fusionado

#### Scenario: Inaccesible
- **WHEN** la consulta por identificador no lo encuentra o no hay permiso
- **THEN** el cliente lo devuelve como inaccesible

### Requirement: Respeto del límite de peticiones

El cliente SHALL respetar los límites de GitHub. Si GitHub indica que el límite está agotado, el cliente MUST NOT volver a consultar antes de la hora de restablecimiento que GitHub comunica.

#### Scenario: Límite agotado
- **WHEN** GitHub responde que se agotó el límite primario o secundario
- **THEN** el sondeo se suspende hasta la hora de restablecimiento, el panel conserva los últimos datos y el tooltip indica hasta cuándo

### Requirement: Tolerancia a fallos de red

Un fallo de red o un error del servidor SHALL dejar visible el último estado conocido en lugar de vaciar el panel. El cliente MUST NOT reintentar de inmediato: espera al siguiente ciclo.

#### Scenario: GitHub inalcanzable
- **WHEN** un sondeo falla por timeout, DNS o error 5xx
- **THEN** el panel conserva los datos del último sondeo correcto y advierte que están desactualizados, con la hora del último éxito

### Requirement: Verificación TLS siempre activa

El cliente SHALL verificar el certificado TLS contra las autoridades del sistema. La verificación MUST NOT poder desactivarse desde la configuración. El cliente SHALL respetar el proxy configurado en el sistema.

#### Scenario: Certificado no confiable
- **WHEN** el certificado del servidor no valida
- **THEN** la conexión falla y se trata como fallo de red; no existe opción para ignorar la verificación

#### Scenario: CA corporativa instalada en el sistema
- **WHEN** un proxy corporativo intercepta TLS con una CA que está en el almacén del sistema
- **THEN** la conexión valida sin configuración adicional
