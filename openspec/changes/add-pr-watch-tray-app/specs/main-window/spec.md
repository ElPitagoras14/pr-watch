## Purpose

Define el panel que aparece junto al icono de bandeja: su forma, su estética (la del popup de usage-monitor-for-claude), los dos bloques de pull requests con filas de dos líneas, sus acciones, el fijado y el tema.

## ADDED Requirements

### Requirement: El panel convive con la bandeja sin reemplazarla

La aplicación SHALL residir permanentemente en la bandeja y SHALL mostrar el panel solo cuando el usuario lo pide. La aplicación MUST NOT mostrar el panel al arrancar.

#### Scenario: Arranque
- **WHEN** la aplicación arranca, esté configurada o no
- **THEN** aparece el icono en la bandeja y no se muestra ninguna ventana, ni siquiera brevemente

#### Scenario: Abrir bajo demanda
- **WHEN** el usuario activa el icono de bandeja o la entrada `Abrir pr-watch`
- **THEN** el panel aparece en primer plano; si ya estaba abierto, pasa al frente en lugar de abrirse un segundo

#### Scenario: Activar el icono con el panel visible
- **WHEN** el panel está visible y el usuario activa de nuevo el icono de bandeja
- **THEN** el panel se oculta

### Requirement: Cerrar el panel no detiene la vigilancia

Cerrar el panel SHALL ocultarlo y dejar la aplicación sondeando. Solo `Salir` desde la bandeja SHALL terminar el proceso.

#### Scenario: Cerrar con el icono de cerrar o con Escape
- **WHEN** el usuario activa el icono de cerrar del panel o pulsa Escape
- **THEN** el panel se oculta y el sondeo continúa

#### Scenario: Reabrir conserva el estado
- **WHEN** el usuario vuelve a abrir el panel
- **THEN** ve los datos del último sondeo de inmediato, sin lista vacía ni espera

### Requirement: Estética del panel

El panel SHALL seguir el lenguaje visual del popup de usage-monitor-for-claude: un panel estrecho sin barra de título del sistema; el nombre de la aplicación en negrita a la izquierda y los iconos de acción a la derecha, sobre el mismo fondo que el resto; secciones con encabezado en mayúsculas, gris y de peso fuerte; filas de etiqueta a la izquierda y valor a la derecha; separadores finos entre secciones; y un pie en gris con la última actualización y la versión. SHALL usar la tipografía de interfaz del sistema.

#### Scenario: Sin decoración del sistema
- **WHEN** el panel aparece
- **THEN** no muestra la barra de título ni los botones de ventana del sistema operativo

#### Scenario: Sección de cuenta
- **WHEN** el panel muestra la sección `CUENTA`
- **THEN** presenta como pares etiqueta/valor el usuario, el proveedor con su ámbito (por ejemplo `github.com · contoso`, o `github.com · Cuenta personal` sin repetir el usuario) y el estado de la conexión

#### Scenario: La acción va al extremo del encabezado
- **WHEN** una sección ofrece una acción sobre toda la lista
- **THEN** aparece como enlace subrayado al extremo derecho de su encabezado, como el `Changelog` de usage-monitor

#### Scenario: Pie
- **WHEN** el panel está visible
- **THEN** su pie indica cuánto hace que se actualizaron los datos, que se refresca solo mientras el panel está abierto, y la versión de la aplicación

### Requirement: Lista de pull requests en dos bloques

El panel SHALL mostrar los pull requests en dos bloques: `MÍOS` (los creados por el usuario) y `POR REVISAR` (con su revisión solicitada o asignados a él). Cada encabezado SHALL indicar el total real del bloque y cada bloque SHALL mostrar como máximo el tope configurado, aplicado por separado. El panel MUST NOT ofrecer desplazamiento: su alto se ajusta al contenido.

#### Scenario: El tope es de cada bloque
- **WHEN** el tope es cuatro y hay seis propios y seis por revisar
- **THEN** el panel muestra cuatro en cada bloque y cada encabezado indica seis

#### Scenario: Cuáles entran
- **WHEN** hay que elegir qué pull requests mostrar
- **THEN** se priorizan los accionables —rotos o listos para fusionar en `MÍOS`, pendientes de tu revisión en `POR REVISAR`— y, a igualdad, los de actualización más reciente

#### Scenario: Ver todos
- **WHEN** el usuario activa `Ver todos` en el encabezado de un bloque
- **THEN** el navegador abre en GitHub la búsqueda equivalente a ese bloque

#### Scenario: El panel se ajusta a lo que muestra
- **WHEN** cambia el número de pull requests visibles
- **THEN** el alto del panel se ajusta al contenido sin dejar hueco ni recortar

#### Scenario: Sin nada pendiente
- **WHEN** no hay pull requests en ninguna relación
- **THEN** el panel lo dice explícitamente en lugar de mostrar dos bloques vacíos

### Requirement: Fila de dos líneas

Cada pull request SHALL ocupar dos líneas. La primera: un punto de color de estado, la referencia (`#142`), el título truncado al ancho disponible y, a la derecha, la etiqueta de estado coloreada. La segunda, en gris y más pequeña: en `MÍOS`, el repositorio, el estado de los checks y las conversaciones sin resolver; en `POR REVISAR`, el repositorio, el autor y cuánto hace que se actualizó.

La etiqueta y el color de estado SHALL seguir este orden de prioridad: `fusionado` / `cerrado` (gris), `conflictos` (rojo), `checks fallidos` (rojo), `cambios pedidos` (ámbar), `listo para fusionar` (verde), `aprobado (N)` (verde), `te toca` en `POR REVISAR` si la revisión del usuario sigue pendiente (ámbar), `sin revisar` (ámbar).

#### Scenario: Aprobaciones sin denominador
- **WHEN** un pull request tiene dos aprobaciones
- **THEN** la etiqueta dice `aprobado (2)` y nunca `2/2`

#### Scenario: Quién aprobó
- **WHEN** el usuario se detiene sobre una fila con aprobaciones
- **THEN** aparece quiénes aprobaron

#### Scenario: Prioridad de estados
- **WHEN** un pull request aprobado tiene además conflictos
- **THEN** la etiqueta dice `conflictos` en rojo

#### Scenario: Abrir en GitHub
- **WHEN** el usuario activa una fila
- **THEN** el navegador predeterminado abre ese pull request

### Requirement: Marcas de novedad en la lista

El panel SHALL distinguir visualmente las filas con novedades no vistas.

#### Scenario: Una fila con novedad
- **WHEN** un pull request acumuló una novedad desde la última vez que se abrió el panel
- **THEN** su fila se distingue de las demás

#### Scenario: Las marcas se limpian al mirar
- **WHEN** el usuario abre el panel y lo cierra
- **THEN** las marcas desaparecen, igual que el punto del icono

#### Scenario: Novedad con el panel abierto
- **WHEN** llega una novedad mientras el panel está abierto
- **THEN** la fila se marca y la lista se actualiza sola

### Requirement: Avisos de estado en el panel

El panel SHALL mostrar en la sección de cuenta, en lugar de los bloques o junto a ellos, cuándo falta configurar la aplicación, cuándo la credencial dejó de ser válida, cuándo los datos están desactualizados y cuándo el sondeo está suspendido por el límite de peticiones.

#### Scenario: Datos desactualizados
- **WHEN** el último sondeo falló
- **THEN** el panel muestra los datos del último sondeo correcto y advierte de que están desactualizados, con su hora

#### Scenario: Sin configurar
- **WHEN** no hay credencial
- **THEN** el panel lo dice y ofrece abrir los ajustes, en lugar de mostrar bloques vacíos

### Requirement: Acciones del panel

El panel SHALL ofrecer sus acciones como iconos en la fila del título, en este orden: actualizar, ajustes, fijar y cerrar. Los iconos SHALL ser los mismos glifos que usa mr-watch (Segoe Fluent Icons / Segoe MDL2 Assets: `E72C`, `E713`, `E718`, `E711`) con un equivalente dibujado cuando esa fuente no exista, y SHALL explicarse al pasar el ratón.

#### Scenario: Actualizar
- **WHEN** el usuario activa el icono de recargar
- **THEN** se ejecuta un sondeo inmediato y la lista refleja el resultado

#### Scenario: Ajustes
- **WHEN** el usuario activa el icono de ajustes
- **THEN** se abre la ventana de ajustes y el panel conserva su contenido

#### Scenario: Fijar
- **WHEN** el usuario activa el icono de fijar
- **THEN** el icono queda resaltado mientras el panel está fijado

#### Scenario: Cada icono se explica
- **WHEN** el usuario se detiene sobre cualquiera de los iconos
- **THEN** aparece una descripción de lo que hace

### Requirement: El panel aparece junto al icono

El panel SHALL aparecer pegado al icono de bandeja cuando el sistema permita conocer su posición, y en la esquina del área de trabajo donde está la bandeja cuando no. El panel MUST NOT poder arrastrarse ni recordar posición.

#### Scenario: Posición conocida
- **WHEN** el sistema informa de dónde está el icono
- **THEN** el panel aparece adyacente a él, dentro de los límites de la pantalla

#### Scenario: Posición desconocida
- **WHEN** el sistema no informa de la posición del icono
- **THEN** el panel aparece en la esquina del área de trabajo junto a la bandeja, sin taparla con la barra de tareas

### Requirement: Fijar el panel

El panel SHALL ocultarse al perder el foco, salvo que esté fijado o que la ventana de ajustes esté abierta. El fijado MUST NOT conservarse entre aperturas.

#### Scenario: Perder el foco lo oculta
- **WHEN** el usuario hace clic fuera del panel sin fijar
- **THEN** el panel se oculta

#### Scenario: Fijado permanece
- **WHEN** el panel está fijado y el usuario trabaja en otra ventana
- **THEN** el panel sigue visible

#### Scenario: El fijado no se hereda
- **WHEN** el usuario fija el panel, lo cierra y lo vuelve a abrir
- **THEN** aparece sin fijar

### Requirement: El tema lo decide el sistema

El panel SHALL adoptar el tema claro u oscuro del sistema y adaptarse en caliente si cambia.

#### Scenario: Escritorio oscuro
- **WHEN** el sistema está en tema oscuro
- **THEN** el panel se dibuja con la paleta oscura de usage-monitor

#### Scenario: Cambio en caliente
- **WHEN** el usuario cambia el tema del sistema con el panel abierto
- **THEN** el panel se adapta sin reiniciar
