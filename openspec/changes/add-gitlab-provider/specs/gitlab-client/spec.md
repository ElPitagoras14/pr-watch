## ADDED Requirements

### Requirement: Un proveedor para la nube y para las instancias propias

El proveedor `gitlab` SHALL servir tanto a `gitlab.com` como a cualquier instancia self-hosted: la única diferencia SHALL ser el host configurado. El proveedor SHALL derivar del host la URL de la API (`<host>/api/graphql`), la URL web, el enlace para crear el token y el conjunto de URL que la aplicación acepta abrir en el navegador. El host MUST NOT aparecer escrito a fuego en ninguna parte del proveedor.

#### Scenario: GitLab cloud
- **WHEN** el host configurado es `https://gitlab.com`
- **THEN** el proveedor consulta `https://gitlab.com/api/graphql` y enlaza a `https://gitlab.com`

#### Scenario: Instancia propia
- **WHEN** el host configurado es `https://gitlab.empresa.com`
- **THEN** el proveedor consulta `https://gitlab.empresa.com/api/graphql` y enlaza a esa misma instancia, sin ninguna petición a `gitlab.com`

#### Scenario: Instancia en un subdirectorio
- **WHEN** el host configurado incluye una ruta, como `https://devops.empresa.com/gitlab`
- **THEN** el proveedor la conserva y consulta `https://devops.empresa.com/gitlab/api/graphql`

#### Scenario: Solo se abren URL de la instancia
- **WHEN** el panel pide abrir una URL que no pertenece al host configurado
- **THEN** la aplicación la rechaza y lo registra, sin abrir el navegador

### Requirement: Cliente de solo lectura

El cliente SHALL limitarse a leer. Contra la API GraphQL de GitLab SHALL enviar únicamente documentos de tipo `query`; el cliente MUST rechazar, antes de enviarlo, cualquier documento que contenga una `mutation` o una `subscription`. Cualquier petición REST SHALL ser `GET`. El token SHALL viajar en la cabecera `Authorization` y MUST NOT aparecer en la query string.

#### Scenario: Una mutación nunca sale
- **WHEN** cualquier parte del código intenta enviar un documento GraphQL que contiene `mutation`
- **THEN** el cliente lo rechaza con un error de programación y no se emite ninguna petición

#### Scenario: El ámbito viaja como variable
- **WHEN** el cliente consulta los merge requests de un grupo
- **THEN** la ruta del grupo viaja como variable de la consulta, nunca concatenada dentro del documento

### Requirement: Token de solo lectura recomendado

La aplicación SHALL indicar al usuario que cree un *personal access token* en su instancia con el único ámbito `read_api`, y SHALL ofrecer el enlace a la página de creación de tokens de esa instancia.

#### Scenario: El usuario ve qué ámbito dar
- **WHEN** el usuario mira la sección de la credencial en la ventana de ajustes con GitLab activo
- **THEN** encuentra `read_api` indicado como único ámbito necesario y un enlace que abre la página de tokens de su instancia

#### Scenario: Token con más permisos
- **WHEN** el usuario usa un token con el ámbito `api` completo
- **THEN** la aplicación funciona igualmente, porque el propio cliente no escribe nunca

### Requirement: Versión mínima de la instancia

El cliente SHALL soportar instancias de GitLab 16 o posterior. Al verificar la credencial SHALL consultar la versión de la instancia y, si es anterior a la mínima soportada, SHALL rechazar la configuración con un mensaje que nombre la versión encontrada y la mínima, en lugar de dejar que una consulta falle después por un campo inexistente.

#### Scenario: Instancia soportada
- **WHEN** la instancia informa una versión igual o posterior a la mínima
- **THEN** la verificación continúa con normalidad

#### Scenario: Instancia demasiado antigua
- **WHEN** la instancia informa una versión anterior a la mínima soportada
- **THEN** la verificación falla indicando la versión encontrada y la mínima requerida, y no se guarda nada

#### Scenario: La instancia no dice su versión
- **WHEN** la consulta de versión no devuelve nada reconocible pero el resto de la verificación funciona
- **THEN** el cliente continúa y deja constancia en el registro, en lugar de bloquear al usuario

### Requirement: Solo campos disponibles en todas las ediciones

El cliente MUST NOT pedir campos exclusivos de las ediciones de pago de GitLab. En particular, el número de aprobaciones requeridas o restantes y la lista propia de quienes pidieron cambios SHALL quedar fuera del documento: el modelo neutro no los necesita y una instancia Community los rechaza. Si aun así la instancia rechaza algún campo, el cliente SHALL devolver un error que nombre el campo y la versión de la instancia, en lugar de propagar el error crudo de GraphQL.

#### Scenario: Instancia Community
- **WHEN** la instancia es de edición Community
- **THEN** el sondeo y la verificación funcionan igual que en una de pago, sin campos rechazados

#### Scenario: Campo rechazado por la instancia
- **WHEN** la instancia rechaza un campo del documento por no existir en ella
- **THEN** el cliente lo clasifica como fallo de servidor con un mensaje que nombra el campo y la versión encontrada, y lo deja en el registro

#### Scenario: La edición queda registrada
- **WHEN** la verificación de la credencial termina
- **THEN** el registro recoge la versión y la edición de la instancia, para poder interpretar después un fallo

### Requirement: Ámbitos que ve el token

El cliente SHALL poder verificar un token por sí solo, sin ámbito, devolviendo el nombre de usuario y los ámbitos elegibles: el espacio de nombres personal del usuario, siempre en primer lugar, y los grupos que el token puede ver, identificados por su ruta completa y ordenados por ella.

#### Scenario: Token con grupos
- **WHEN** GitLab acepta el token y el usuario ve varios grupos
- **THEN** el cliente devuelve su nombre de usuario y las rutas completas de esos grupos, ordenadas, con el espacio personal primero

#### Scenario: Subgrupos
- **WHEN** el token ve el subgrupo `empresa/plataforma/red`
- **THEN** ese ámbito se ofrece con su ruta completa, no solo con el último segmento

#### Scenario: Token sin grupos
- **WHEN** GitLab acepta el token pero el usuario no pertenece a ningún grupo visible
- **THEN** el cliente devuelve el usuario y solo el espacio personal, sin tratarlo como error

#### Scenario: Token inválido
- **WHEN** GitLab responde `401`
- **THEN** el cliente devuelve "credencial inválida"

### Requirement: Verificación de la credencial

Verificar una credencial con su ámbito SHALL comprobar que GitLab acepta el token y que con él se puede consultar el ámbito configurado. El resultado SHALL distinguir token inválido, ámbito inexistente o inaccesible, límite agotado y fallo de red.

#### Scenario: Credencial válida
- **WHEN** GitLab acepta el token y el grupo configurado es accesible
- **THEN** la verificación devuelve el nombre de usuario

#### Scenario: Grupo inaccesible
- **WHEN** el token es válido pero el grupo no existe o el token no lo ve, caso en que GitLab responde `404`
- **THEN** la verificación devuelve "sin acceso al ámbito", distinto de "credencial inválida"

#### Scenario: Espacio personal de otro
- **WHEN** el ámbito es el espacio personal de un usuario distinto al del token
- **THEN** la verificación devuelve "sin acceso", porque solo se vigila el propio

#### Scenario: Host que no es una instancia de GitLab
- **WHEN** el host configurado responde pero no es una API de GitLab
- **THEN** la verificación falla como fallo de red o de servidor, con un mensaje que invita a revisar la dirección de la instancia

### Requirement: Consulta de merge requests por relación

El cliente SHALL obtener los merge requests abiertos del ámbito configurado en las tres relaciones del usuario: creados por él, con su revisión solicitada y asignados a él. Si el ámbito es un grupo, la consulta SHALL incluir sus subgrupos. Cada consulta SHALL traer en la misma respuesta los datos que necesita el modelo neutro: aprobaciones, estado del pipeline, conflictos y discusiones sin resolver, sin peticiones individuales por merge request.

#### Scenario: Las tres relaciones
- **WHEN** se ejecuta un sondeo
- **THEN** se consultan las tres relaciones y sus resultados se unifican

#### Scenario: Un merge request en dos relaciones
- **WHEN** un mismo merge request aparece en más de una relación
- **THEN** aparece una sola vez, clasificado por la relación de mayor prioridad: autor antes que revisor, y revisor antes que asignado

#### Scenario: Subgrupos incluidos
- **WHEN** el ámbito es `empresa` y el merge request vive en `empresa/plataforma/red`
- **THEN** aparece en el panel

#### Scenario: Paginación
- **WHEN** una relación devuelve más resultados de los que caben en una página
- **THEN** el cliente recorre las páginas siguientes hasta agotar el conjunto

#### Scenario: Una relación falla y las otras no
- **WHEN** una de las tres consultas falla y las demás responden
- **THEN** el cliente devuelve el resultado marcado como incompleto, con el motivo del fallo, para que el sondeo no purgue nada

### Requirement: El sondeo cabe en el presupuesto de la instancia

GitLab puntúa la complejidad de cada consulta y rechaza la que pase de su límite. El documento de sondeo SHALL mantenerse holgadamente por debajo de ese límite, SHALL pedir a la instancia la puntuación de la propia consulta y SHALL dejar aviso en el registro cuando se acerque al techo.

#### Scenario: Margen suficiente
- **WHEN** se ejecuta el documento de sondeo con el tamaño de página configurado
- **THEN** su puntuación de complejidad queda por debajo del límite que la instancia comunica, con margen para que una instancia más estricta tampoco lo rechace

#### Scenario: Aviso al acercarse al techo
- **WHEN** la puntuación supera el 80 % del límite comunicado
- **THEN** el cliente lo registra, nombrando puntuación y límite

#### Scenario: Consulta rechazada por compleja
- **WHEN** la instancia rechaza el documento por exceder su límite de complejidad
- **THEN** el cliente lo clasifica como fallo de servidor con un mensaje que lo explica, el panel conserva los últimos datos y no se purga nada

### Requirement: Traducción al modelo neutro

El cliente SHALL traducir la respuesta de GitLab al modelo neutro de `forge-provider` con estas reglas: el identificador es el identificador global del merge request; el repositorio es la ruta completa del proyecto; el número es el `iid` del proyecto; las aprobaciones son los usuarios que han aprobado; hay cambios pedidos si algún revisor dejó su revisión en estado de cambios solicitados; la revisión del usuario sigue pendiente si figura como revisor y su revisión no ha empezado o está a medias; los checks se resumen desde el estado del pipeline de la última versión, y son "ninguno" si el merge request no tiene pipeline; hay conflictos si GitLab declara el merge request en conflicto; las conversaciones sin resolver son las discusiones resolubles que siguen sin resolver; está listo para fusionar si no es borrador, no tiene conflictos, el pipeline no falla, nadie pidió cambios y está aprobado.

Un merge request SHALL contar como aprobado si GitLab lo declara aprobado **o** si hay al menos un aprobador: en una instancia sin reglas de aprobación configuradas, la lista de aprobadores es la única señal fiable. El cliente MUST NOT deducir "listo para fusionar" del estado detallado de fusión que publica GitLab, porque ese estado da por fusionable un merge request que nadie ha aprobado.

#### Scenario: Aprobaciones sin denominador
- **WHEN** dos personas aprobaron un merge request
- **THEN** el modelo indica dos aprobaciones y sus nombres de usuario, sin inventar un número requerido

#### Scenario: Proyecto sin pipelines
- **WHEN** un merge request pertenece a un proyecto sin integración continua
- **THEN** los checks quedan como "ninguno" y eso no impide que figure como listo para fusionar

#### Scenario: Aprobado sin regla de aprobación
- **WHEN** un merge request tiene un aprobador pero la instancia no declara el merge request como aprobado, por no haber regla que lo exija
- **THEN** el modelo lo cuenta como aprobado

#### Scenario: Fusionable pero sin revisar
- **WHEN** un merge request no tiene conflictos ni reglas que lo bloqueen, pero nadie lo ha aprobado
- **THEN** el modelo NO lo da por listo para fusionar

#### Scenario: Estado de fusión aún desconocido
- **WHEN** GitLab todavía está calculando si el merge request tiene conflictos
- **THEN** el modelo conserva el último valor conocido en lugar de oscilar

#### Scenario: Referencia del merge request
- **WHEN** el panel muestra un merge request número 142
- **THEN** lo referencia como `!142` y lo nombra "MR", sin que la interfaz tenga ese vocabulario escrito a fuego

#### Scenario: Borrador
- **WHEN** el título del merge request está marcado como borrador en GitLab
- **THEN** el modelo lo marca como borrador y no lo da por listo para fusionar

### Requirement: Estado de merge requests que dejaron de aparecer

Cuando un merge request conocido deja de aparecer en las consultas de abiertos, el cliente SHALL poder consultar su estado actual por identificador, en lotes y no uno por uno, para distinguir fusionado, cerrado e inaccesible.

#### Scenario: Fusionado
- **WHEN** un merge request conocido desaparece de las consultas y su estado indica que se fusionó
- **THEN** el cliente lo devuelve como fusionado

#### Scenario: Inaccesible
- **WHEN** la consulta por identificador no lo encuentra o no hay permiso
- **THEN** el cliente lo devuelve como inaccesible

#### Scenario: Consulta en lote
- **WHEN** hay que consultar el estado de quince merge requests
- **THEN** el cliente lo resuelve agrupando identificadores, no con quince peticiones

### Requirement: Respeto del límite de peticiones

El cliente SHALL respetar los límites de la instancia. Si GitLab indica que el límite está agotado, el cliente MUST NOT volver a consultar antes del momento de restablecimiento que la instancia comunica; si no comunica ninguno, SHALL esperar un margen prudencial.

#### Scenario: Límite agotado
- **WHEN** GitLab responde `429` con el momento de restablecimiento
- **THEN** el sondeo se suspende hasta ese momento, el panel conserva los últimos datos y el tooltip indica hasta cuándo

#### Scenario: Límite agotado sin cabecera
- **WHEN** GitLab responde `429` sin indicar cuándo se restablece
- **THEN** el cliente espera un margen por defecto antes de volver a consultar

### Requirement: Tolerancia a fallos de red y verificación TLS

Un fallo de red o un error del servidor SHALL dejar visible el último estado conocido en lugar de vaciar el panel, y el cliente MUST NOT reintentar de inmediato. El cliente SHALL verificar el certificado TLS contra las autoridades del sistema y la verificación MUST NOT poder desactivarse desde la configuración.

#### Scenario: Instancia inalcanzable
- **WHEN** un sondeo falla por timeout, DNS o error 5xx
- **THEN** el panel conserva los datos del último sondeo correcto y advierte que están desactualizados, con la hora del último éxito

#### Scenario: CA corporativa instalada en el sistema
- **WHEN** la instancia propia presenta un certificado de una CA corporativa que está en el almacén del sistema
- **THEN** la conexión valida sin configuración adicional en la aplicación

#### Scenario: Certificado no confiable
- **WHEN** el certificado de la instancia no valida contra el almacén del sistema
- **THEN** la conexión falla y se trata como fallo de red, con un mensaje que invita a instalar la CA en el sistema; no existe opción para ignorar la verificación
