## Purpose

Define la marca de pr-watch: un glifo monocromo de pull request dibujado por código, el mismo para la bandeja, las ventanas y el ejecutable.

## ADDED Requirements

### Requirement: Marca monocroma dibujada por código

La aplicación SHALL tener un símbolo propio de pull request: dos ramas con sus nodos, una de ellas con la flecha de vuelta hacia la otra. El símbolo SHALL ser monocromo, sin disco ni fondo, y SHALL dibujarse por código con medidas relativas al lado. El repositorio MUST NOT contener el icono como archivo binario.

#### Scenario: Legible a tamaño de bandeja
- **WHEN** la marca se dibuja a 16 píxeles
- **THEN** sus trazos y nodos siguen distinguiéndose

#### Scenario: Color según la barra de tareas
- **WHEN** la barra de tareas usa tema oscuro
- **THEN** el glifo de bandeja se dibuja claro; con barra clara, oscuro

#### Scenario: Un solo origen
- **WHEN** alguien cambia el dibujo de la marca
- **THEN** cambian a la vez el icono de bandeja, el de las ventanas y el del ejecutable

### Requirement: El ejecutable lleva su icono

El ejecutable de Windows SHALL llevar la marca embebida en los tamaños de 16 a 256 píxeles, generada durante el empaquetado. Un fallo al generarla MUST NOT impedir el empaquetado.

#### Scenario: El Explorador lo muestra
- **WHEN** el usuario ve el ejecutable en el Explorador o en Alt+Tab
- **THEN** aparece la marca y no el icono genérico

#### Scenario: Sin poder generar el icono
- **WHEN** la generación del icono falla durante el empaquetado
- **THEN** el empaquetado avisa y termina, y el ejecutable sale sin icono
