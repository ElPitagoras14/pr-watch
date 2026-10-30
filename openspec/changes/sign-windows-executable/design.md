## Context

`build-windows` en `.github/workflows/release.yml` construye `dist/pr-watch.exe` con `uv run build.py` (PyInstaller `--onefile --windowed`), comprueba que existe y lo sube como artefacto; `release` lo adjunta después al GitHub Release. Ningún paso firma el binario. El runner es `windows-latest`, que trae el SDK de Windows (y por tanto `signtool.exe`) preinstalado, sin pasos adicionales de setup.

La decisión de usar un certificado autofirmado —en vez de una CA pública como HARICA— ya está tomada: resuelve el caso de uso principal (equipos del dominio de Telconet, vía GPO) a coste cero, a cambio de no quitar el aviso de SmartScreen fuera de ese dominio.

## Goals / Non-Goals

**Goals:**
- Firmar `pr-watch.exe` con Authenticode usando un certificado autofirmado, con sellado de tiempo, en el job `build-windows`.
- Que el paso se salte sin fallar el build cuando el secreto no está configurado (desarrollo local, forks, PRs externos).
- Dejar documentado en el repositorio qué garantiza la firma y qué no.

**Non-Goals:**
- Automatizar la generación del certificado o su renovación: es un paso manual de IT, fuera del pipeline.
- Automatizar la distribución del certificado público por GPO.
- Eliminar el aviso de SmartScreen fuera del dominio de Telconet (eso requiere una CA pública; queda para un cambio futuro si se decide).
- Firmar el binario de Linux: Authenticode no existe fuera de Windows.

## Decisions

### Herramienta de firma: `signtool.exe`

`windows-latest` ya lo trae (parte del Windows SDK), así que no hay que instalar nada nuevo. La alternativa cross-platform (`osslsigncode`) tendría sentido si se firmara desde un runner Linux, pero `build-windows` ya corre en Windows: usar la herramienta nativa es menos codigo y menos superficie de fallo.

### Formato y almacenamiento del secreto: PFX en base64 + contraseña, como dos secretos separados

Los secretos de GitHub Actions son texto, así que el `.pfx` (binario) tiene que viajar codificado; base64 es el estándar de facto para esto en workflows de firma. La contraseña va en un secreto propio (`WINDOWS_CODESIGN_PFX_PASSWORD`) en vez de incrustada en el nombre de archivo o en texto plano en el YAML, para que GitHub la enmascare en los logs igual que al PFX.

Alternativa descartada: guardar el `.pfx` como un "Environment secret" con un approval gate. Es más seguro para builds disparados por PRs externos, pero este workflow solo corre en pushes a `main` (ya protegido por reglas de rama), así que el gate añadiría fricción sin beneficio real aquí.

### Dónde vive el certificado: generado fuera del repo, documentado pero no versionado

El `.pfx` (clave privada) nunca toca el repositorio ni en claro ni cifrado: solo existe como secreto de GitHub y en el almacén de quien lo genera. El repo documenta el comando de referencia para generarlo (`New-SelfSignedCertificate` con EKU de firma de código) para que IT no tenga que inventar el procedimiento, pero ejecutarlo es responsabilidad suya, fuera de CI.

### Paso condicional: `if: ${{ secrets.WINDOWS_CODESIGN_PFX_BASE64 != '' }}`

GitHub Actions permite referenciar `secrets.*` directamente en la condición `if` de un step (no así a nivel de `job`). Con esto, el step de firma se omite entero —ni se decodifica nada, ni se invoca `signtool`— cuando el secreto no existe, y el resto del job sigue exactamente igual que hoy: `dist/pr-watch.exe` sin firmar, mismo artefacto subido. No hace falta una bandera de configuración aparte: la presencia del secreto es la señal.

### Sellado de tiempo contra una TSA pública

Sin sellado de tiempo, la firma deja de validarse cuando el certificado expira (los autofirmados típicamente se generan con 1-5 años de validez). Con sellado de tiempo RFC 3161, Windows puede verificar que la firma se hizo *mientras el certificado era válido*, y la acepta indefinidamente después. Se usa un servidor de sellado público (ej. `http://timestamp.digicert.com`); el sellado de tiempo no valida la identidad del firmante, solo atestigua el instante, así que funciona igual de bien con un certificado autofirmado que con uno de una CA pública.

Comando de referencia:
```
signtool sign /f cert.pfx /p %PFX_PASSWORD% /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 dist\pr-watch.exe
```

### Dónde insertar el paso

Después de "Comprobar que existe" (que ya falla el build si PyInstaller no generó el `.exe`) y antes de `actions/upload-artifact`. Así nunca se intenta firmar un archivo que no existe, y si la firma falla, el artefacto sin firmar no llega a subirse — mejor fallar ruidoso ahí que publicar en silencio un binario sin firmar cuando se esperaba uno firmado.

### Verificación tras firmar

Un paso corto con `Get-AuthenticodeSignature` que confirme `Status -ne 'NotSigned'` (no que sea `Valid`: con un certificado autofirmado, el runner no lo tiene como raíz de confianza, así que el estado esperado es `UnknownError`/`NotTrusted`, no `Valid`). Esto detecta un fallo silencioso de `signtool` sin exigir que el runner confíe en el certificado.

## Risks / Trade-offs

- **El aviso de SmartScreen sigue apareciendo fuera del dominio de Telconet** → Mitigación: documentado en el README sin ambigüedad; la vía de salida (CA pública tipo HARICA) queda registrada como opción futura, no resuelta aquí.
- **El `.pfx` decodificado toca el disco del runner en claro, aunque sea brevemente** → Mitigación: se decodifica a un archivo temporal dentro del workspace efímero del runner, se usa inmediatamente y se borra explícitamente al final del step; el runner completo se destruye al terminar el job de todas formas.
- **El certificado autofirmado expira y nadie se entera hasta que falla una firma** → Mitigación: el sellado de tiempo evita que los binarios *ya firmados* dejen de ser válidos; la renovación del certificado sigue siendo manual y queda fuera de este cambio — IT debe llevar registro de la fecha de expiración.
- **Alguien rota el secreto o lo borra sin avisar** → Mitigación: el step condicional hace que el pipeline no falle, solo deje de firmar; es una degradación silenciosa en vez de un build roto, lo cual es deseable aquí pero significa que una rotación accidental no se nota sola — se menciona en la spec como comportamiento esperado, no como fallo a alertar.

## Migration Plan

1. IT/el usuario genera el certificado autofirmado con EKU de firma de código (comando de referencia en el README) y lo exporta a `.pfx` con contraseña.
2. Se codifica el `.pfx` en base64 y se crean los dos secretos del repositorio: `WINDOWS_CODESIGN_PFX_BASE64` y `WINDOWS_CODESIGN_PFX_PASSWORD`.
3. Se añade el step de firma (condicional) al job `build-windows`.
4. Se valida en un push real a `main`: el job debe firmar, verificar con `Get-AuthenticodeSignature` y subir el artefacto firmado.
5. Por separado y fuera de este repositorio, IT distribuye el certificado público (`.cer`, sin la clave privada) como raíz de confianza vía GPO en el dominio de Telconet.

**Rollback**: borrar los dos secretos (el step se salta solo, sin tocar el YAML) o revertir el commit que añade el step. En ambos casos el pipeline vuelve a producir el `.exe` sin firmar, sin ningún otro efecto.

## Open Questions

Ninguna pendiente: el certificado se genera y gestiona fuera de este cambio, a discreción de IT (sujeto, validez, almacén de claves).
