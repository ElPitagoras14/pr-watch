## Purpose

Define qué entrega una publicación: los dos ejecutables, el tag que los ata a un commit concreto y el release que los pone al alcance de quien sigue el README.

## ADDED Requirements

### Requirement: Un binario por plataforma en cada release

Cada release SHALL adjuntar exactamente dos ejecutables, construidos a partir del mismo commit: `pr-watch.exe` para Windows de 64 bits y `pr-watch` para Linux x86-64. Los nombres de descarga SHALL ser esos, los mismos que nombra el README, para que las instrucciones de instalación sigan siendo ciertas.

#### Scenario: Descarga desde el README
- **WHEN** un usuario sigue las instrucciones de instalación y entra al último release
- **THEN** encuentra `pr-watch.exe` y `pr-watch` como archivos descargables

#### Scenario: Los dos binarios son del mismo commit
- **WHEN** se publica una versión
- **THEN** ambos ejecutables se construyeron desde el commit que el tag señala

### Requirement: Los binarios se construyen con la orden del proyecto

Cada ejecutable SHALL construirse con la orden de construcción que ya existe en el repositorio, en su plataforma nativa y con las versiones fijadas en el bloqueo de dependencias. El workflow MUST NOT duplicar ni reimplementar los argumentos de empaquetado.

#### Scenario: Cambia la configuración de empaquetado
- **WHEN** se modifica la lógica de construcción del proyecto
- **THEN** el pipeline publica binarios construidos con esa lógica nueva, sin tocar el workflow

### Requirement: El ejecutable publicado declara la versión publicada

El ejecutable de Windows SHALL llevar embebidos el icono y el recurso de versión correspondientes a la versión que se publica, y el panel de la aplicación SHALL mostrar esa misma versión.

#### Scenario: Propiedades del ejecutable de Windows
- **WHEN** el usuario abre las propiedades de `pr-watch.exe` descargado de un release
- **THEN** la versión de archivo y de producto coinciden con la versión del release

### Requirement: Tag anotado por versión

Cada publicación SHALL crear un tag anotado `v<versión>` sobre el commit construido. El tag MUST NOT moverse una vez creado.

#### Scenario: Primera publicación
- **WHEN** se publica la versión `0.1.0`
- **THEN** existe el tag `v0.1.0` apuntando al commit construido

#### Scenario: Intento de reescribir un tag
- **WHEN** una ejecución posterior intenta etiquetar una versión que ya tiene tag
- **THEN** el tag existente queda intacto y apuntando al commit original

### Requirement: Release con notas derivadas del historial

Cada publicación SHALL crear un GitHub Release sobre el tag correspondiente, titulado con la versión, con notas generadas a partir de los commits posteriores al tag anterior. El primer release SHALL cubrir todo el historial hasta ese punto.

#### Scenario: Release posterior al primero
- **WHEN** se publica una versión y existe un tag anterior
- **THEN** las notas listan los commits entre el tag anterior y el nuevo

#### Scenario: Primer release del repositorio
- **WHEN** se publica la primera versión y no hay tag anterior
- **THEN** el release se crea igual, con notas que cubren el historial disponible

### Requirement: El release dice contra qué sistema se construyó Linux

Las notas del release SHALL indicar la versión de distribución en que se construyó el binario de Linux y las bibliotecas de sistema que necesita, de modo que el usuario pueda saber antes de descargar si su equipo lo soporta.

#### Scenario: Usuario en una distribución antigua
- **WHEN** un usuario con una glibc más antigua que la del runner mira el release
- **THEN** encuentra indicada la distribución de construcción y las bibliotecas requeridas, sin tener que ejecutar el binario para descubrir que no arranca
