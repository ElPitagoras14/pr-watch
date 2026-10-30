## Purpose

Define lo que se entrega: un ejecutable único y portable por plataforma, `pr-watch.exe` en Windows y `pr-watch` en Linux, que no requiere Python ni instalación.

## ADDED Requirements

### Requirement: Un ejecutable único por plataforma

El proyecto SHALL producir un único archivo ejecutable por plataforma: `pr-watch.exe` para Windows 10/11 de 64 bits y `pr-watch` (ELF x86-64) para Linux. Cada uno SHALL contener el intérprete, las dependencias de Python y la interfaz, de modo que el usuario MUST NOT necesitar Python, `uv` ni ningún paquete de Python instalado.

#### Scenario: Windows sin Python
- **WHEN** el usuario copia `pr-watch.exe` a un Windows 10/11 sin Python y lo ejecuta
- **THEN** la aplicación arranca en la bandeja

#### Scenario: Linux sin Python del proyecto
- **WHEN** el usuario copia `pr-watch` a un Linux con escritorio que tiene GTK 3, WebKit2GTK 4.1 y Ayatana AppIndicator, le da permiso de ejecución y lo ejecuta
- **THEN** la aplicación arranca en la bandeja, sin crear entornos virtuales ni instalar paquetes de Python

#### Scenario: Faltan bibliotecas del sistema en Linux
- **WHEN** el binario de Linux arranca en un sistema al que le falta WebKit2GTK o AppIndicator
- **THEN** termina con un mensaje que nombra la biblioteca que falta y el paquete que la proporciona, en lugar de un volcado de error de Python

#### Scenario: Sin consola en Windows
- **WHEN** el usuario ejecuta `pr-watch.exe`
- **THEN** no aparece ninguna ventana de consola

### Requirement: Portable y sin instalación

Los ejecutables MUST NOT requerir instalador ni permisos elevados. Todo lo que escriben SHALL ir al directorio de configuración del usuario, nunca junto al ejecutable.

#### Scenario: Ejecutable en una carpeta de solo lectura
- **WHEN** el ejecutable está en una carpeta donde el usuario no puede escribir
- **THEN** la aplicación funciona igual, porque configuración, estado, log y credencial de respaldo viven en el directorio de configuración

### Requirement: Construcción reproducible

Cada ejecutable SHALL construirse con una sola orden desde un clon limpio en su plataforma, usando las versiones fijadas en el bloqueo de dependencias.

#### Scenario: Construir en Windows
- **WHEN** el desarrollador ejecuta la orden de construcción en Windows con un clon limpio
- **THEN** obtiene `dist/pr-watch.exe` con el icono y la versión embebidos

#### Scenario: Construir en Linux
- **WHEN** el desarrollador ejecuta la misma orden en Linux, o en WSL desde Windows, con un clon limpio y las bibliotecas de desarrollo del sistema instaladas
- **THEN** obtiene `dist/pr-watch`
