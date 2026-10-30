## Purpose

Define cuándo se consulta la forja, qué estado se guarda entre arranques, qué cuenta como novedad y qué se oculta o se purga.

## ADDED Requirements

### Requirement: Sondeo periódico

La aplicación SHALL consultar al proveedor a un intervalo configurable, 60 segundos por defecto, con un suelo de 30 segundos. Cada sondeo SHALL traer el listado y todo su detalle en un solo paso.

#### Scenario: Primer sondeo
- **WHEN** la aplicación arranca con credencial
- **THEN** sondea de inmediato, sin esperar al primer intervalo

#### Scenario: Ritmo
- **WHEN** pasa el intervalo configurado desde el último sondeo
- **THEN** se ejecuta otro sondeo y el panel se actualiza con su resultado

#### Scenario: El sondeo no bloquea la interfaz
- **WHEN** un sondeo está en curso
- **THEN** el panel, la bandeja y la ventana de ajustes siguen respondiendo

### Requirement: Actualización manual

El panel y el menú de bandeja SHALL ofrecer actualizar ahora, que fuerza un sondeo inmediato.

#### Scenario: Actualización forzada
- **WHEN** el usuario pide actualizar ahora
- **THEN** se ejecuta un sondeo de inmediato y el temporizador se reinicia

#### Scenario: Actualización ya en curso
- **WHEN** el usuario pide actualizar mientras un sondeo está en curso
- **THEN** no se lanza un sondeo concurrente; se espera al que ya corre

#### Scenario: Límite de peticiones agotado
- **WHEN** el usuario pide actualizar mientras el sondeo está suspendido por el límite de GitHub
- **THEN** no se emite ninguna petición y el panel indica hasta cuándo dura la suspensión

### Requirement: Estado persistido entre arranques

El estado anterior de cada pull request SHALL guardarse en disco, en el directorio de configuración y separado por proveedor, para poder distinguir qué cambió.

#### Scenario: No avisar dos veces
- **WHEN** la aplicación se cierra tras detectar que `#142` fue aprobado, y se vuelve a abrir
- **THEN** no vuelve a tratar esa aprobación como novedad

#### Scenario: Primer arranque sin estado
- **WHEN** no existe archivo de estado
- **THEN** el primer sondeo establece la línea base y no genera ninguna novedad

#### Scenario: Estado corrupto o ilegible
- **WHEN** el archivo de estado existe pero no se puede interpretar
- **THEN** la aplicación lo descarta y arranca como si fuera el primer arranque, sin abortar

#### Scenario: Escritura atómica
- **WHEN** la aplicación se interrumpe mientras guarda el estado
- **THEN** el archivo de estado anterior sigue íntegro

### Requirement: Detección de novedades

Entre dos sondeos, SHALL clasificarse como novedad únicamente: un pull request nuevo entra en alguna de las tres relaciones, cambia el número de aprobaciones, se piden cambios, los checks pasan a fallidos o a correctos, aparecen conflictos, el pull request pasa a fusionado o cerrado, o cambia el número de conversaciones sin resolver.

#### Scenario: Aprobación nueva
- **WHEN** un pull request pasa de 1 a 2 aprobaciones entre dos sondeos
- **THEN** se registra una novedad para ese pull request

#### Scenario: Cambio irrelevante
- **WHEN** entre dos sondeos solo cambia la fecha de actualización
- **THEN** no se registra novedad

#### Scenario: Pull request nuevo a revisar
- **WHEN** aparece un pull request con revisión solicitada al usuario que no estaba en el sondeo anterior
- **THEN** se registra una novedad

### Requirement: Filtrado de ruido

Los pull requests en borrador SHALL ocultarse del panel. Los fusionados o cerrados SHALL permanecer visibles durante el plazo configurado (15 minutos por defecto) desde que se detectó el cambio, y luego desaparecer solos.

#### Scenario: Borrador oculto
- **WHEN** un pull request propio es borrador
- **THEN** no aparece en el panel

#### Scenario: Borrador que deja de serlo
- **WHEN** un pull request deja de ser borrador
- **THEN** aparece en el panel y se trata como pull request nuevo a efectos de novedades

#### Scenario: Fusionado con caducidad
- **WHEN** un pull request se detecta como fusionado
- **THEN** permanece en el panel marcado como fusionado durante el plazo y después desaparece

#### Scenario: Caducidad tras reinicio
- **WHEN** la aplicación se reinicia y un fusionado ya superó su plazo según el estado guardado
- **THEN** no vuelve a aparecer

### Requirement: Purga de pull requests que dejan de ser accesibles

Un pull request que desaparece del listado y cuyo estado resulta inaccesible SHALL purgarse del estado persistido únicamente si el sondeo completó con éxito las tres consultas de relación. Un sondeo con cualquier consulta fallida MUST NOT purgar nada.

#### Scenario: Se pierde el acceso al repositorio
- **WHEN** el usuario pierde acceso a un repositorio y sus pull requests desaparecen de las tres consultas, que se completan con éxito
- **THEN** se eliminan del estado y del panel

#### Scenario: La purga es silenciosa
- **WHEN** un pull request se purga por inaccesible
- **THEN** no se registra novedad ni se aplica la caducidad de los fusionados

#### Scenario: Un sondeo fallido no purga
- **WHEN** una de las tres consultas falla y las otras devuelven menos pull requests de los conocidos
- **THEN** el estado persistido se conserva íntegro

#### Scenario: Deja la relación pero sigue abierto
- **WHEN** un pull request sigue abierto pero ya no tiene relación con el usuario, por ejemplo porque le quitaron la revisión
- **THEN** sale del panel sin generar novedad
