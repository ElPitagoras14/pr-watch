## Purpose

Define las notificaciones del sistema: apagadas por defecto, limitadas a lo accionable, sin repeticiones, y que al activarse llevan al pull request.

## ADDED Requirements

### Requirement: Las notificaciones vienen apagadas

Las notificaciones del sistema SHALL estar desactivadas por defecto. El canal normal de aviso es el punto sobre el icono.

#### Scenario: Instalación nueva
- **WHEN** la aplicación corre sin configuración previa
- **THEN** no emite notificaciones, por muchas novedades que detecte

#### Scenario: Activación explícita
- **WHEN** el usuario activa las notificaciones en la ventana de ajustes
- **THEN** empiezan a emitirse desde el siguiente sondeo

### Requirement: Solo lo accionable notifica

Con las notificaciones activadas, la aplicación SHALL notificar únicamente: un pull request propio queda listo para fusionar, un pull request propio se rompe por conflictos o checks fallidos, se piden cambios en un pull request propio, o llega un pull request nuevo a la revisión del usuario.

#### Scenario: Llega algo a revisar
- **WHEN** aparece un pull request nuevo con la revisión del usuario solicitada
- **THEN** se emite una notificación

#### Scenario: Novedad no accionable
- **WHEN** cambia el número de conversaciones sin resolver o un pull request se fusiona
- **THEN** la novedad cuenta para el punto pero no notifica

### Requirement: Una notificación por hecho

La aplicación MUST NOT repetir la notificación de un hecho mientras no cambie.

#### Scenario: Sin repetición
- **WHEN** un pull request sigue listo para fusionar durante varios sondeos
- **THEN** se notificó una sola vez

#### Scenario: El hecho se repite tras revertirse
- **WHEN** un pull request se rompe, se arregla y vuelve a romperse
- **THEN** se notifica en cada transición a roto

#### Scenario: Agrupación
- **WHEN** un mismo sondeo produce más de tres hechos notificables
- **THEN** se emite una única notificación resumida

### Requirement: Activar una notificación lleva al pull request

Activar una notificación SHALL abrir en el navegador el pull request que la originó; activar una resumida SHALL abrir el panel.

#### Scenario: Apertura desde la notificación
- **WHEN** el usuario activa una notificación sobre `#142`
- **THEN** el navegador abre `#142`

#### Scenario: Notificación agrupada
- **WHEN** el usuario activa una notificación resumida
- **THEN** se abre el panel

### Requirement: Degradación sin servicio de notificaciones

La ausencia de un servicio de notificaciones MUST NOT impedir el funcionamiento de la aplicación.

#### Scenario: Sin servicio disponible
- **WHEN** las notificaciones están activadas pero el sistema no puede emitirlas
- **THEN** la aplicación sigue funcionando y registra el fallo una sola vez
