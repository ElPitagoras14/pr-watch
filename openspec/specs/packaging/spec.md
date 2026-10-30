## Purpose

Define cómo se empaqueta pr-watch y qué diagnóstico da el binario de Linux cuando no puede arrancar, para que el usuario sepa qué le falta en lugar de ver una traza.

## Requirements

### Requirement: Diagnóstico de arranque fiel al binario de Linux

Cuando el binario empaquetado de Linux no puede cargar su enlace con GObject, la aplicación SHALL terminar con un mensaje que incluya el error real de carga y, si el sistema tiene una glibc más antigua que la mínima del binario, las dos versiones de glibc. Dentro del binario empaquetado, el mensaje MUST NOT recomendar instalar un paquete de Python del sistema, porque el binario no lo usa. Ejecutada desde el código fuente, la aplicación SHALL seguir indicando el paquete del sistema que proporciona PyGObject.

#### Scenario: Binario en una distribución con glibc demasiado antigua
- **WHEN** el binario empaquetado arranca en un sistema cuya glibc es más antigua que la mínima con la que se construyó
- **THEN** termina con un mensaje que nombra la glibc del sistema y la mínima requerida, incluye el error de carga original y no recomienda `python3-gi`

#### Scenario: Binario que no carga GObject por otra causa
- **WHEN** el binario empaquetado no puede cargar su enlace con GObject y la glibc del sistema es suficiente
- **THEN** termina con un mensaje que incluye el error de carga original, sin recomendar un paquete de Python del sistema

#### Scenario: Ejecución desde el código fuente sin PyGObject
- **WHEN** la aplicación se ejecuta desde el código fuente en un Linux sin PyGObject disponible
- **THEN** termina indicando el paquete del sistema que proporciona PyGObject, como hasta ahora

#### Scenario: Error registrado en el log
- **WHEN** el arranque termina por cualquiera de los fallos anteriores
- **THEN** el error de carga original queda también en el registro de la aplicación
