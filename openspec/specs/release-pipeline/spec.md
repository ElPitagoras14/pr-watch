## Purpose

Define el pipeline que construye y publica los binarios de pr-watch, incluido el piso de glibc del binario de Linux y la comprobación de que arranca antes de publicar.

## Requirements

### Requirement: Piso de glibc declarado para el binario de Linux

El binario de Linux publicado SHALL ejecutarse en cualquier distribución x86-64 con glibc 2.35 o más nueva que tenga GTK 3, WebKit2GTK 4.1 y Ayatana AppIndicator. El pipeline SHALL construirlo en un entorno fijado cuya glibc sea esa mínima, de modo que el piso solo cambie mediante un cambio deliberado del workflow. El binario MUST NOT llevar dentro bibliotecas de sistema que también cargan GTK o WebKit, para no mezclar dos versiones de ellas en el mismo proceso.

#### Scenario: Distribución en el piso
- **WHEN** el binario publicado se ejecuta en Ubuntu 22.04 o Debian 12 con las bibliotecas de GTK, WebKit y AppIndicator instaladas
- **THEN** la aplicación supera el chequeo de bibliotecas y arranca

#### Scenario: Distribución más reciente
- **WHEN** el binario publicado se ejecuta en Debian 13 o Ubuntu 24.04 con las mismas bibliotecas
- **THEN** la aplicación supera el chequeo de bibliotecas y arranca, igual que con los binarios construidos antes de este cambio

### Requirement: Prueba de arranque antes de publicar

Antes de crear el tag, el pipeline SHALL ejecutar el binario de Linux construido en al menos una distribución con la glibc mínima y otra con la más reciente soportada, y SHALL comprobar que supera el chequeo de bibliotecas. Si cualquiera de las dos falla, MUST NOT crearse el tag ni el release.

#### Scenario: El binario no carga en la distribución mínima
- **WHEN** el binario construido no supera el chequeo de bibliotecas en la distribución con la glibc mínima
- **THEN** el pipeline falla antes del tag y no se publica nada

#### Scenario: El binario carga en ambos extremos
- **WHEN** el binario supera el chequeo en las dos distribuciones
- **THEN** el pipeline continúa hacia el tag y el release
