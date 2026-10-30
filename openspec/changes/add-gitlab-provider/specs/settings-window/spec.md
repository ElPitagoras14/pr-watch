## ADDED Requirements

### Requirement: Elegir la forja y la instancia

La ventana SHALL ofrecer, antes que la credencial, qué forja vigilar: un selector con los proveedores implementados y, cuando el proveedor elegido admita varias instancias, un campo con la dirección de la instancia. Para GitLab el campo SHALL venir con `https://gitlab.com` y SHALL poder sustituirse por la dirección de una instancia propia. Cambiar el proveedor o la instancia SHALL descartar la verificación en curso y volver a pedir token y ámbito.

#### Scenario: Selector de proveedor
- **WHEN** el usuario abre la ventana de ajustes
- **THEN** encuentra el proveedor activo seleccionado y puede elegir otro de los implementados

#### Scenario: Campo de instancia solo donde aplica
- **WHEN** el proveedor elegido es GitHub
- **THEN** no aparece campo de instancia, porque el proveedor solo sirve a `github.com`

#### Scenario: Instancia propia
- **WHEN** el usuario elige GitLab y escribe `https://gitlab.empresa.com`
- **THEN** la verificación del token y la lista de ámbitos se hacen contra esa instancia, no contra `gitlab.com`

#### Scenario: Cambiar de proveedor descarta lo verificado
- **WHEN** el usuario verifica un token y después cambia el proveedor o la instancia
- **THEN** la verificación deja de darse por buena, el selector de ámbito se inhabilita y el guardado de la credencial también, hasta volver a verificar

#### Scenario: Credencial ya guardada para esa forja
- **WHEN** el usuario elige un proveedor e instancia para los que ya hay un token guardado
- **THEN** la ventana lo indica, verifica el guardado por su cuenta para llenar la lista de ámbitos, y no obliga a volver a escribirlo

#### Scenario: Instancia inalcanzable
- **WHEN** la dirección escrita no responde, no es una instancia de GitLab o es de una versión no soportada
- **THEN** la ventana lo dice de forma distinguible de "token inválido" y no guarda nada

### Requirement: Los textos de la credencial los aporta el proveedor

La ventana MUST NOT llevar escritos a fuego los textos propios de una forja. El nombre de la forja, los permisos o ámbitos que debe tener el token, el enlace para crearlo, la etiqueta del ámbito vigilado y el sustantivo de lo vigilado SHALL venir del proveedor activo.

#### Scenario: Con GitLab activo
- **WHEN** el proveedor activo es GitLab
- **THEN** la ventana pide un token con el ámbito `read_api`, enlaza a la página de tokens de esa instancia, llama al ámbito "Grupo o espacio personal" y habla de MR

#### Scenario: Con GitHub activo
- **WHEN** el proveedor activo es GitHub
- **THEN** la ventana sigue pidiendo un *fine-grained token* con sus permisos de lectura, enlaza a la página de GitHub, llama al ámbito "Cuenta u organización" y habla de PR

### Requirement: Cambiar de forja se aplica al guardar

Guardar un cambio de proveedor o de instancia SHALL aplicarlo sin reiniciar la aplicación: el sondeo pasa a la forja nueva con su credencial y su ámbito, y el panel deja de mostrar lo que venía de la anterior.

#### Scenario: Cambio aplicado en caliente
- **WHEN** el usuario cambia de GitHub a GitLab y guarda
- **THEN** el siguiente sondeo consulta GitLab, el panel se vacía de los pull requests de GitHub y el tooltip pasa a hablar de la nueva forja

#### Scenario: Sin credencial para la forja nueva
- **WHEN** el usuario cambia a una forja para la que no hay token y guarda sin verificar uno
- **THEN** la ventana se niega a guardar la credencial y lo indica, igual que en la primera configuración

#### Scenario: Cancelar no cambia de forja
- **WHEN** el usuario cambia el proveedor en la ventana y cierra sin guardar
- **THEN** la aplicación sigue sondeando la forja anterior y nada se escribe

## MODIFIED Requirements

### Requirement: Primero el token, después la organización

La ventana SHALL pedir la credencial en dos pasos, siempre contra la forja elegida: primero el token, que se verifica contra esa forja; después qué vigilar, que se elige de una lista: el ámbito personal del usuario, siempre en primer lugar, y los ámbitos que ese token puede ver —organizaciones en GitHub, grupos en GitLab—. El selector de ámbito SHALL estar inhabilitado hasta que el token se haya verificado. Elegir un ámbito SHALL comprobar el acceso a él antes de habilitar el guardado. La aplicación MUST NOT guardar una credencial que no haya superado las dos comprobaciones.

#### Scenario: Campos iniciales sin credencial
- **WHEN** se abre la ventana de ajustes sin token guardado
- **THEN** el token aparece vacío y enmascarado, con el foco, y el selector de ámbito aparece inhabilitado

#### Scenario: Campos iniciales con credencial guardada
- **WHEN** se abre la ventana con un token guardado
- **THEN** el token aparece vacío y enmascarado sin revelar el guardado, la ventana verifica el guardado por su cuenta para llenar la lista, y el ámbito configurado aparece seleccionado

#### Scenario: Pegar el token
- **WHEN** el usuario pega el token con Ctrl+V
- **THEN** el campo lo recibe desde el portapapeles del sistema y lo muestra enmascarado

#### Scenario: Se indican los permisos necesarios
- **WHEN** el usuario mira la sección de la credencial
- **THEN** encuentra los permisos de solo lectura que pide la forja activa y un enlace que abre en el navegador su página de creación de tokens

#### Scenario: Token válido
- **WHEN** el usuario verifica un token que la forja acepta
- **THEN** la ventana muestra `Conectado como <usuario>`, llena el selector con los ámbitos que ve el token, ordenados por nombre, y lo habilita

#### Scenario: El ámbito personal
- **WHEN** el usuario elige su cuenta o espacio personal y el token ve repositorios suyos
- **THEN** la ventana lo confirma y habilita el guardado, y el panel pasa a mostrar lo que le incumbe de esos repositorios

#### Scenario: El token no lista ámbitos
- **WHEN** el token es válido pero no revela ninguna organización ni grupo
- **THEN** el selector ofrece el ámbito personal y escribir uno a mano, y lo indica

#### Scenario: Un ámbito que no está en la lista
- **WHEN** el ámbito buscado no aparece en la lista
- **THEN** el selector incluye la opción de escribirlo a mano, admitiendo rutas con subgrupos cuando la forja las use

#### Scenario: Elegir un ámbito
- **WHEN** el usuario elige un ámbito y el token tiene acceso a sus repositorios
- **THEN** la ventana lo confirma y habilita el guardado

#### Scenario: Token rechazado
- **WHEN** la forja rechaza el token
- **THEN** la ventana lo dice, el selector sigue inhabilitado, no se guarda nada y se señala que hay que renovar el token

#### Scenario: Sin acceso al ámbito
- **WHEN** el token es válido pero no da acceso al ámbito elegido
- **THEN** la ventana lo distingue del token inválido e indica qué revisar: en GitHub el dueño del token o la aprobación de la organización, en GitLab la pertenencia al grupo

#### Scenario: La forja inalcanzable
- **WHEN** no hay conexión o el certificado no valida
- **THEN** la ventana lo distingue de los dos casos anteriores

#### Scenario: La verificación no congela la ventana
- **WHEN** una comprobación está en curso
- **THEN** la ventana sigue respondiendo, indica que está comprobando y el sondeo no se detiene

#### Scenario: Cambiar el token tras verificar
- **WHEN** el usuario verifica con éxito y después modifica el token
- **THEN** la verificación deja de darse por buena, el selector de ámbito se inhabilita y el guardado de la credencial también, hasta volver a verificar

#### Scenario: Conservar el token guardado
- **WHEN** el usuario guarda sin haber escrito ningún token y sin cambiar de forja ni de ámbito
- **THEN** el token guardado se conserva y solo se aplican el resto de ajustes
