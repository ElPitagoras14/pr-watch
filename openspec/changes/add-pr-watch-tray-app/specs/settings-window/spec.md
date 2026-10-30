## Purpose

Define la ventana de ajustes: dónde se configuran la organización y el token con verificación previa, el resto de preferencias con control propio, el guardado en caliente y el cierre de sesión.

## ADDED Requirements

### Requirement: La configuración vive en una ventana aparte

La aplicación SHALL ofrecer sus ajustes en una ventana propia, distinta del panel, con el mismo lenguaje visual del panel y su propio cierre. El panel MUST NOT cambiar de contenido mientras la ventana de ajustes está abierta.

#### Scenario: Abrir los ajustes
- **WHEN** el usuario activa el icono de ajustes del panel
- **THEN** aparece la ventana de ajustes en primer plano, con el panel aún visible detrás

#### Scenario: Una sola ventana
- **WHEN** el usuario pide los ajustes y la ventana ya está abierta
- **THEN** esa ventana pasa al frente en lugar de abrirse una segunda

#### Scenario: Se puede mover
- **WHEN** el usuario arrastra la cabecera de la ventana de ajustes
- **THEN** la ventana se mueve, pese a no tener barra de título del sistema

#### Scenario: El panel no se escapa
- **WHEN** la ventana de ajustes está abierta y el panel pierde el foco
- **THEN** el panel permanece visible hasta que la ventana de ajustes se cierre

#### Scenario: Cerrar el panel cierra los ajustes
- **WHEN** el usuario cierra el panel con la ventana de ajustes abierta
- **THEN** la ventana de ajustes se cierra con él, descartando lo no guardado

### Requirement: Primero el token, después la organización

La ventana SHALL pedir la credencial en dos pasos: primero el token, que se verifica contra GitHub; después qué vigilar, que se elige de una lista: la cuenta personal del usuario, siempre en primer lugar, y las organizaciones que ese token puede ver. El selector de organización SHALL estar inhabilitado hasta que el token se haya verificado. Elegir una organización SHALL comprobar el acceso a ella antes de habilitar el guardado. La aplicación MUST NOT guardar una credencial que no haya superado las dos comprobaciones.

#### Scenario: Campos iniciales sin credencial
- **WHEN** se abre la ventana de ajustes sin token guardado
- **THEN** el token aparece vacío y enmascarado, con el foco, y el selector de organización aparece inhabilitado

#### Scenario: Campos iniciales con credencial guardada
- **WHEN** se abre la ventana con un token guardado
- **THEN** el token aparece vacío y enmascarado sin revelar el guardado, la ventana verifica el guardado por su cuenta para llenar la lista, y la organización configurada aparece seleccionada

#### Scenario: Pegar el token
- **WHEN** el usuario pega el token con Ctrl+V
- **THEN** el campo lo recibe desde el portapapeles del sistema y lo muestra enmascarado

#### Scenario: Se indican los permisos necesarios
- **WHEN** el usuario mira la sección de la credencial
- **THEN** encuentra los permisos de solo lectura requeridos y un enlace que abre en el navegador la página de GitHub para crear un fine-grained token

#### Scenario: Token válido
- **WHEN** el usuario verifica un token que GitHub acepta
- **THEN** la ventana muestra `Conectado como <usuario>`, llena el selector con las organizaciones que ve el token, ordenadas por nombre, y lo habilita

#### Scenario: La cuenta personal
- **WHEN** el usuario elige su cuenta personal y el token ve repositorios suyos
- **THEN** la ventana lo confirma y habilita el guardado, y el panel pasa a mostrar los pull requests de los repositorios de esa cuenta

#### Scenario: El token no lista organizaciones
- **WHEN** el token es válido pero ni las organizaciones del usuario ni los repositorios accesibles revelan ninguna
- **THEN** el selector ofrece la cuenta personal y escribir una organización a mano, y lo indica

#### Scenario: Una organización que no está en la lista
- **WHEN** la organización buscada no aparece en la lista
- **THEN** el selector incluye la opción de escribirla a mano

#### Scenario: Elegir una organización
- **WHEN** el usuario elige una organización y el token tiene acceso a sus repositorios
- **THEN** la ventana lo confirma y habilita el guardado

#### Scenario: Token rechazado
- **WHEN** GitHub rechaza el token
- **THEN** la ventana lo dice, el selector sigue inhabilitado, no se guarda nada y se señala que hay que renovar el token

#### Scenario: Sin acceso a la organización
- **WHEN** el token es válido pero no da acceso a la organización elegida
- **THEN** la ventana lo distingue del token inválido e indica que hay que revisar el dueño del token o la aprobación de la organización

#### Scenario: GitHub inalcanzable
- **WHEN** no hay conexión o el certificado no valida
- **THEN** la ventana lo distingue de los dos casos anteriores

#### Scenario: La verificación no congela la ventana
- **WHEN** una comprobación está en curso
- **THEN** la ventana sigue respondiendo, indica que está comprobando y el sondeo no se detiene

#### Scenario: Cambiar el token tras verificar
- **WHEN** el usuario verifica con éxito y después modifica el token
- **THEN** la verificación deja de darse por buena, el selector de organización se inhabilita y el guardado de la credencial también, hasta volver a verificar

#### Scenario: Conservar el token guardado
- **WHEN** el usuario guarda sin haber escrito ningún token y sin cambiar la organización
- **THEN** el token guardado se conserva y solo se aplican el resto de ajustes

### Requirement: Ajustes con control propio

La ventana SHALL ofrecer control sobre el intervalo de sondeo, las notificaciones del sistema y el tope de pull requests por bloque.

#### Scenario: Intervalo
- **WHEN** el usuario fija un intervalo por debajo de 30 segundos
- **THEN** la ventana lo dice y lo eleva a 30

#### Scenario: Un tope para cada bloque
- **WHEN** el usuario fija el tope en cuatro
- **THEN** el panel muestra hasta cuatro propios y hasta cuatro por revisar

#### Scenario: Tope fuera de rango
- **WHEN** el usuario intenta fijar un tope menor que uno o mayor que veinte
- **THEN** la ventana lo ajusta al extremo más cercano

#### Scenario: Lo que no tiene control propio
- **WHEN** el usuario quiere cambiar un ajuste sin control en la ventana
- **THEN** la ventana ofrece abrir `config.toml` en el editor predeterminado

### Requirement: Guardar aplica sin reiniciar

Guardar SHALL escribir `config.toml` y el token y SHALL aplicar los cambios a la aplicación en marcha. Cancelar o cerrar SHALL descartar lo editado sin tocar nada.

#### Scenario: Guardar
- **WHEN** el usuario guarda
- **THEN** la configuración queda escrita, la ventana se cierra y los nuevos valores rigen desde ese momento

#### Scenario: El tope nuevo se ve enseguida
- **WHEN** el usuario cambia el tope y guarda
- **THEN** el panel se redibuja sin esperar al siguiente sondeo

#### Scenario: Credencial nueva sin reiniciar
- **WHEN** el usuario guarda una credencial verificada
- **THEN** la aplicación empieza a sondear con ella, aunque llevara toda la sesión sin token

#### Scenario: Cancelar
- **WHEN** el usuario cancela o cierra con cambios sin guardar
- **THEN** no se escribe nada

#### Scenario: No se puede guardar
- **WHEN** la configuración no se puede escribir en disco
- **THEN** la aplicación avisa y sigue con los valores que tenía

### Requirement: Primera configuración en la ventana de ajustes

Cuando no haya token en ninguna fuente, la ventana de ajustes SHALL aparecer la primera vez que el usuario abra el panel en la sesión, con el foco en el campo que falte. La aplicación MUST NOT usar diálogos del sistema operativo para pedir la credencial.

#### Scenario: Primera vez que se abre el panel
- **WHEN** el usuario abre el panel y no hay token
- **THEN** aparece además la ventana de ajustes, con el foco en el token

#### Scenario: No vuelve a insistir
- **WHEN** el usuario cerró la ventana sin configurar y vuelve a abrir el panel en la misma sesión
- **THEN** el panel se abre sin la ventana de ajustes

### Requirement: Cerrar sesión desde Ajustes

La ventana SHALL ofrecer cerrar sesión, que borra la credencial guardada, solo cuando haya una al abrir la ventana. Cerrar sesión MUST NOT cerrar la ventana.

#### Scenario: Cerrar sesión borra la credencial
- **WHEN** el usuario activa cerrar sesión
- **THEN** la aplicación borra el token, deja de sondear y el panel muestra el aviso de falta de configuración

#### Scenario: La ventana queda lista para iniciar sesión de nuevo
- **WHEN** el usuario cierra sesión
- **THEN** la ventana sigue abierta, con el token vacío, la verificación anterior descartada, el selector de organización inhabilitado y la organización configurada conservada en `config.toml`

#### Scenario: Sin credencial no hay sesión que cerrar
- **WHEN** el usuario abre la ventana y no hay token guardado
- **THEN** la opción de cerrar sesión no está disponible
