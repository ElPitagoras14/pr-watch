## Purpose

Define el aviso de novedades sin ver: un contador interno que se muestra como un punto sobre el icono de bandeja y se resume en el tooltip, y que vuelve a cero al mirar el panel.

## ADDED Requirements

### Requirement: El contador es un buzón, no un marcador de pendientes

La aplicación SHALL contar las novedades ocurridas desde la última vez que el usuario abrió el panel. El contador MUST NOT representar el número de pull requests pendientes.

#### Scenario: Incremento por novedad
- **WHEN** un sondeo detecta tres novedades según `pr-polling`
- **THEN** el contador aumenta en tres

#### Scenario: Pendientes sin novedad
- **WHEN** hay cinco pull requests abiertos pero ninguno cambió
- **THEN** el contador no cambia

### Requirement: Punto de novedades sobre el icono

El icono de bandeja SHALL mostrar un punto de color cuando el contador sea mayor que cero, y ningún punto cuando valga cero. El icono MUST NOT dibujar el número ni cambiar de color según el estado de los pull requests.

#### Scenario: Con novedades
- **WHEN** el contador pasa de 0 a 1
- **THEN** aparece el punto sobre el icono

#### Scenario: Más novedades
- **WHEN** el contador pasa de 1 a 5
- **THEN** el icono no cambia: el punto ya estaba

#### Scenario: Legible en barras claras y oscuras
- **WHEN** el icono se muestra sobre una barra de tareas clara u oscura
- **THEN** tanto el glifo como el punto se distinguen del fondo

#### Scenario: Redibujado solo ante cambios
- **WHEN** un sondeo termina sin que cambie la presencia del punto
- **THEN** el icono no se vuelve a entregar al sistema

### Requirement: Abrir el panel pone el contador a cero

Abrir el panel SHALL poner el contador a cero, quitar el punto del icono y, al cerrarse el panel, limpiar las marcas de novedad de la lista. Abrir el menú de bandeja MUST NOT ponerlo a cero.

#### Scenario: Puesta a cero
- **WHEN** el usuario abre el panel con el contador en 3
- **THEN** el contador queda en 0 y el punto desaparece

#### Scenario: Abrir el menú no basta
- **WHEN** el usuario abre el menú de bandeja y lo cierra sin abrir el panel
- **THEN** el contador no cambia

#### Scenario: Novedad con el panel abierto
- **WHEN** llega una novedad mientras el panel está visible
- **THEN** el contador sigue en cero y la fila se marca

### Requirement: El contador arranca en cero

El contador MUST NOT persistir entre ejecuciones.

#### Scenario: Cambios ocurridos con la aplicación cerrada
- **WHEN** la aplicación estuvo cerrada mientras aprobaban un pull request, y luego arranca
- **THEN** el primer sondeo reconoce el cambio contra el estado guardado, pero el contador queda en 0

### Requirement: Tooltip del icono

El icono SHALL exponer un tooltip que resuma el estado, donde el sistema lo soporte.

#### Scenario: Con novedades
- **WHEN** el contador vale 3
- **THEN** el tooltip dice `pr-watch — 3 sin ver`

#### Scenario: Sin novedades
- **WHEN** el contador vale 0
- **THEN** el tooltip indica cuántos pull requests se vigilan y la hora del último sondeo correcto

#### Scenario: Datos desactualizados o suspendido
- **WHEN** el último sondeo falló o el sondeo está suspendido por el límite de peticiones
- **THEN** el tooltip lo indica y desde o hasta cuándo

#### Scenario: Sin configurar
- **WHEN** no hay token o la credencial es inválida
- **THEN** el tooltip indica que falta configurar la aplicación y que hay que abrir el panel
