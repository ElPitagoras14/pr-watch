## Purpose

Define el pipeline de integración y publicación en GitHub Actions: cuándo corre, qué comprueba antes de construir, en qué orden encadena sus etapas y qué garantiza cuando se repite.

## ADDED Requirements

### Requirement: Disparador en `main` gobernado por la versión

El pipeline SHALL dispararse en cada push a la rama por defecto del repositorio. Su primera etapa, `check-version`, SHALL leer la versión del proyecto y determinar si ya existe el tag `v<versión>` en el repositorio. Si existe, el pipeline MUST terminar en verde sin construir, etiquetar ni publicar nada. Si no existe, SHALL continuar con el resto de las etapas. Publicar una versión SHALL consistir, por tanto, en subir a la rama por defecto un commit que sube la versión.

#### Scenario: Commit que sube la versión
- **WHEN** se sube a `main` un commit que cambia la versión del proyecto a una que no tiene tag
- **THEN** `check-version` publica esa versión como salida y el pipeline sigue a las etapas de verificación, construcción, etiquetado y publicación

#### Scenario: Commit que no toca la versión
- **WHEN** se sube a `main` un commit cuya versión ya tiene tag `v<versión>`
- **THEN** el pipeline termina en verde tras `check-version`, sin construir ni publicar, y la ejecución indica que no había nada que publicar

#### Scenario: Pull request abierto
- **WHEN** se abre o actualiza un pull request hacia `main`
- **THEN** el pipeline de publicación no crea tags ni releases

### Requirement: La versión tiene una sola fuente de verdad

La versión que usa el pipeline SHALL ser la misma que usan el ejecutable y el panel. `check-version` SHALL fallar de forma explícita si las fuentes de la versión divergen entre sí, nombrando los valores en conflicto, en lugar de elegir una.

#### Scenario: Versiones divergentes
- **WHEN** `pyproject.toml` declara una versión y el paquete declara otra
- **THEN** `check-version` falla con un mensaje que nombra ambos valores y el pipeline no construye nada

#### Scenario: Versión mal formada
- **WHEN** la versión no tiene la forma `MAJOR.MINOR.PATCH`
- **THEN** `check-version` falla con un mensaje que nombra el valor leído

### Requirement: Puerta de verificación antes de construir

El pipeline SHALL ejecutar las pruebas, el chequeo de estilo y el chequeo de tipos del proyecto antes de construir cualquier ejecutable. Si alguno falla, el pipeline MUST NOT construir, etiquetar ni publicar. La verificación SHALL usar las mismas órdenes documentadas para el desarrollo local, sin reimplementarlas en el workflow.

#### Scenario: Pruebas rojas en un commit que sube la versión
- **WHEN** la versión es nueva pero las pruebas, `ruff` o `pyright` fallan
- **THEN** el pipeline falla en la verificación y no existe ningún tag ni release para esa versión

#### Scenario: Verificación en verde
- **WHEN** pruebas, estilo y tipos pasan
- **THEN** el pipeline continúa con la construcción de los binarios

### Requirement: Orden de las etapas

Las etapas SHALL encadenarse de modo que cada una dependa del éxito de la anterior: `check-version` → verificación → `build` → `tag` → `release`. El tag MUST NOT crearse antes de que existan los dos binarios, y el release MUST NOT crearse antes de que exista el tag.

#### Scenario: Falla la construcción de una plataforma
- **WHEN** el binario de Linux se construye pero el de Windows falla
- **THEN** no se crea el tag ni el release, y el repositorio queda sin rastro de esa versión publicada

#### Scenario: Falla la creación del tag
- **WHEN** el push del tag falla
- **THEN** no se crea el release

### Requirement: Repetible sin efectos duplicados

Relanzar el pipeline sobre un commit ya publicado MUST NOT crear un tag duplicado, mover un tag existente ni publicar un segundo release de la misma versión.

#### Scenario: Re-ejecución manual de una ejecución ya publicada
- **WHEN** se relanza la ejecución de un commit cuya versión ya fue publicada
- **THEN** `check-version` detecta el tag existente y la ejecución termina en verde sin tocar el tag ni el release

#### Scenario: Carrera entre dos ejecuciones
- **WHEN** dos ejecuciones del pipeline intentan etiquetar la misma versión
- **THEN** una crea el tag y la otra falla o termina sin publicar, pero el tag existente nunca se reescribe apuntando a otro commit

### Requirement: Permisos mínimos y sin secretos nuevos

El workflow SHALL usar el token propio de GitHub Actions, con permiso de escritura sobre el contenido del repositorio únicamente para empujar el tag y crear el release. MUST NOT requerir secretos adicionales ni permisos más amplios de los necesarios.

#### Scenario: Clon nuevo del repositorio
- **WHEN** alguien clona el repositorio y lo sube a su propia cuenta de GitHub
- **THEN** el pipeline funciona sin configurar ningún secreto

### Requirement: El entorno de construcción se declara en el pipeline

El pipeline SHALL instalar explícitamente las dependencias de sistema que la construcción necesita en cada plataforma, incluidas las bibliotecas de desarrollo de GTK/GObject que requiere PyGObject en Linux, y SHALL fijar la versión del runner en lugar de usar una etiqueta móvil, porque el runner determina la glibc contra la que queda enlazado el binario.

#### Scenario: Runner de Linux sin bibliotecas de desarrollo
- **WHEN** la etapa de construcción en Linux prepara el entorno
- **THEN** instala las bibliotecas de desarrollo necesarias antes de sincronizar dependencias, y `uv sync` compila PyGObject sin error

#### Scenario: El runner cambia de versión aguas arriba
- **WHEN** GitHub mueve la etiqueta `ubuntu-latest` a una versión nueva
- **THEN** el pipeline sigue construyendo en la versión fijada, y el piso de glibc del binario no cambia sin un cambio deliberado en el workflow
