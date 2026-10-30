# Firma de código del ejecutable de Windows

`pr-watch.exe` se firma en el pipeline de release (`build-windows` en `.github/workflows/release.yml`) con un certificado autofirmado de Telconet, vía `signtool`. Este documento es la referencia para generar o rotar ese certificado; generarlo y distribuirlo es responsabilidad de IT, fuera del pipeline.

## Generar el certificado

En una máquina Windows, con PowerShell como administrador:

```powershell
$cert = New-SelfSignedCertificate `
  -Subject "CN=Telconet" `
  -Type CodeSigningCert `
  -KeyUsage DigitalSignature `
  -KeyExportPolicy Exportable `
  -KeyAlgorithm RSA `
  -KeyLength 2048 `
  -CertStoreLocation Cert:\CurrentUser\My `
  -NotAfter (Get-Date).AddYears(5) `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")

$pwd = Read-Host -AsSecureString -Prompt "Contraseña del .pfx"
Export-PfxCertificate -Cert $cert -FilePath codesign.pfx -Password $pwd
```

El EKU `1.3.6.1.5.5.7.3.3` (Code Signing) es lo que hace que Windows acepte el certificado para Authenticode.

## Secretos del repositorio

El `.pfx` tiene que viajar como texto en los secretos de GitHub Actions, así que se codifica en base64:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("codesign.pfx")) | Set-Clipboard
```

Se crean dos secretos en el repositorio (Settings → Secrets and variables → Actions):

- `WINDOWS_CODESIGN_PFX_BASE64`: el contenido del portapapeles anterior.
- `WINDOWS_CODESIGN_PFX_PASSWORD`: la contraseña usada al exportar el `.pfx`.

Si cualquiera de los dos falta o se borra, el pipeline sigue publicando `dist/pr-watch.exe` sin firmar, sin fallar el build.

## Distribuir el certificado público (fuera de este repositorio)

Para que el nombre de editor se muestre como confiable dentro del dominio de Telconet, exporta el certificado público (sin la clave privada) y distribúyelo por GPO:

```powershell
Export-Certificate -Cert $cert -FilePath codesign.cer
```

El `.cer` se importa como raíz de confianza (`Trusted Publishers` / `Trusted Root Certification Authorities`, según la política) vía Directiva de Grupo. Esto está fuera del alcance de este repositorio.

## Rotación

Antes de que expire el certificado (`-NotAfter` arriba), repite el proceso completo: genera uno nuevo, actualiza los dos secretos del repositorio y vuelve a distribuir el `.cer` por GPO. El sellado de tiempo (RFC 3161) en cada firma hace que los binarios ya publicados con el certificado anterior sigan siendo válidos después de que expire.
