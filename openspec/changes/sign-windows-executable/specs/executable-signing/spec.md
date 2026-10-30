## ADDED Requirements

### Requirement: El ejecutable de Windows se firma con Authenticode cuando hay un certificado configurado

El job `build-windows` del pipeline de release SHALL firmar `dist/pr-watch.exe` con Authenticode usando `signtool`, usando el certificado y la contraseña provistos como secretos del repositorio, siempre que ambos secretos estén configurados.

#### Scenario: El secreto del certificado esta configurado

- **WHEN** el job `build-windows` construye `dist/pr-watch.exe` y los secretos `WINDOWS_CODESIGN_PFX_BASE64` y `WINDOWS_CODESIGN_PFX_PASSWORD` existen en el repositorio
- **THEN** el pipeline decodifica el certificado, firma `dist/pr-watch.exe` con él, y el artefacto que se sube (`pr-watch-windows`) contiene el binario firmado

#### Scenario: La firma incluye un sello de tiempo

- **WHEN** el pipeline firma `dist/pr-watch.exe`
- **THEN** la firma incluye un sello de tiempo RFC 3161 obtenido de una autoridad de sellado pública, de modo que la firma sigue siendo válida después de que el certificado expire

### Requirement: El pipeline sigue produciendo un ejecutable sin firmar cuando no hay certificado configurado

El job `build-windows` SHALL completar la construcción y publicación del artefacto exactamente igual que sin este cambio cuando el secreto del certificado no está configurado, sin fallar el build por su ausencia.

#### Scenario: El secreto del certificado no esta configurado

- **WHEN** el job `build-windows` corre (en local, en un fork, o en un repositorio donde no se configuraron los secretos de firma) y `WINDOWS_CODESIGN_PFX_BASE64` no existe o está vacío
- **THEN** el paso de firma se omite por completo, no se invoca `signtool`, y el job sube `dist/pr-watch.exe` sin firmar como hace hoy, sin marcar el job como fallido por esa razón

### Requirement: Un fallo real de firma detiene la publicación

Si los secretos de firma están configurados pero la operación de firma falla (contraseña incorrecta, certificado corrupto, `signtool` no encuentra el archivo, fallo de red al sellar tiempo), el job `build-windows` SHALL fallar en vez de subir un artefacto sin firmar cuando se esperaba uno firmado.

#### Scenario: La firma falla con el secreto presente

- **WHEN** el secreto del certificado está configurado pero `signtool` termina con un código de error, o la verificación posterior (`Get-AuthenticodeSignature`) reporta el archivo como no firmado
- **THEN** el job `build-windows` termina en fallo antes de subir el artefacto, y no se publica ningún binario para esa ejecución

### Requirement: El secreto de firma no se expone en texto plano fuera de los secretos de GitHub

El `.pfx` (clave privada del certificado) SHALL permanecer fuera del repositorio en todo momento: no se versiona, no se incrusta en el YAML del workflow, y el archivo temporal que lo materializa en el disco del runner durante la firma SHALL eliminarse explícitamente al terminar el paso de firma.

#### Scenario: Materializacion temporal del certificado en el runner

- **WHEN** el paso de firma decodifica el secreto `WINDOWS_CODESIGN_PFX_BASE64` en un archivo `.pfx` dentro del workspace del runner para pasárselo a `signtool`
- **THEN** ese archivo `.pfx` se borra explícitamente antes de que termine el paso, independientemente de si la firma tuvo éxito o falló
