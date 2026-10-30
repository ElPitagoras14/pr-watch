## Purpose

Permite iterar sobre la interfaz sin arrancar la aplicación ni tocar GitHub: el panel y la ventana de ajustes se abren en un navegador normal con datos de ejemplo, usando exactamente los mismos archivos que la aplicación.

## ADDED Requirements

### Requirement: Vista previa en el navegador

El proyecto SHALL ofrecer una forma de abrir el panel y la ventana de ajustes en un navegador corriente, servidos desde los mismos archivos HTML, CSS y JS que usa la aplicación, con datos de ejemplo en lugar de datos reales. La vista previa MUST NOT necesitar token ni red.

#### Scenario: Retocar el CSS
- **WHEN** el desarrollador cambia el CSS del panel y recarga el navegador
- **THEN** ve el cambio sin reiniciar ni empaquetar nada

#### Scenario: Mismo código que la aplicación
- **WHEN** algo se ve bien en la vista previa
- **THEN** se ve igual en la aplicación, porque no hay una copia aparte de la interfaz

### Requirement: Escenarios de ejemplo

La vista previa SHALL permitir elegir entre escenarios de ejemplo que cubran al menos: sin configurar, sin pull requests, bloques llenos por encima del tope, todos los estados de fila, filas con novedad, datos desactualizados y límite de peticiones agotado. SHALL permitir alternar tema claro y oscuro.

#### Scenario: Cambiar de escenario
- **WHEN** el desarrollador elige otro escenario
- **THEN** el panel se redibuja con esos datos

#### Scenario: Tema
- **WHEN** el desarrollador alterna el tema
- **THEN** el panel se dibuja con la otra paleta

#### Scenario: Acciones sin efecto
- **WHEN** en la vista previa se activa una acción que en la aplicación llama al proceso (actualizar, abrir en GitHub, guardar ajustes)
- **THEN** la acción se registra en la consola del navegador en lugar de fallar
