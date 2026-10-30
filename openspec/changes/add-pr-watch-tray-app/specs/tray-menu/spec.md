## Purpose

Define el icono de bandeja como residencia de la aplicación y las acciones fijas de su menú, incluida la forma de abrir el panel en escritorios Linux que no entregan el clic al icono.

## ADDED Requirements

### Requirement: El icono es la residencia

La aplicación SHALL residir en la bandeja del sistema de forma permanente. Activar el icono SHALL mostrar u ocultar el panel donde el sistema entregue ese clic a la aplicación.

#### Scenario: Clic en Windows
- **WHEN** el usuario hace clic izquierdo sobre el icono en Windows
- **THEN** el panel se muestra, o se oculta si ya estaba visible

#### Scenario: Escritorio que no entrega el clic
- **WHEN** el escritorio Linux abre el menú al hacer clic en lugar de avisar a la aplicación
- **THEN** el usuario abre el panel con la primera entrada del menú, `Abrir pr-watch`

### Requirement: Acciones fijas del menú

El menú SHALL incluir siempre `Abrir pr-watch`, `Actualizar ahora` y `Salir`, y SHALL funcionar con el panel cerrado.

#### Scenario: Acciones siempre presentes
- **WHEN** el menú se abre en cualquier estado, incluso sin pull requests, con GitHub inalcanzable o sin configurar
- **THEN** las tres acciones están presentes y operativas

#### Scenario: Salir
- **WHEN** el usuario activa `Salir`
- **THEN** la aplicación guarda su estado, cierra sus ventanas, retira el icono y termina

### Requirement: Una sola instancia

La aplicación SHALL ejecutarse como una única instancia por usuario.

#### Scenario: Segundo arranque
- **WHEN** el usuario arranca la aplicación y ya hay una corriendo
- **THEN** la segunda termina sin crear otro icono, y la primera muestra su panel
