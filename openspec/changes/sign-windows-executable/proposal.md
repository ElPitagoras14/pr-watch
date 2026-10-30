## Why

`pr-watch.exe` se publica sin firmar: Windows lo marca como "Editor desconocido" en Propiedades → Firmas digitales y SmartScreen avisa al abrirlo, incluso dentro de la red de Telconet. Un certificado autofirmado no elimina el aviso de SmartScreen fuera del dominio —eso exige una CA pública, evaluada aparte (HARICA, ~50 €/año) y descartada por ahora—, pero sí da un nombre de editor verificable y, distribuido por GPO como raíz de confianza, elimina el aviso dentro de la red de Telconet, que es donde se usa el binario hoy.

## What Changes

- Se añade un paso de firma (`signtool`) al final del job `build-windows` de `.github/workflows/release.yml`, después de construir `dist/pr-watch.exe` y antes de subirlo como artefacto.
- El certificado autofirmado (`.pfx`) se genera una sola vez, fuera del pipeline, por el usuario o por IT, y se guarda como secretos de GitHub: el `.pfx` codificado en base64 y su contraseña, por separado.
- La firma incluye sellado de tiempo (timestamping) contra una autoridad de sellado pública, para que la firma siga siendo válida después de que el certificado expire.
- Si el secreto del certificado no está configurado, el paso de firma se salta sin fallar el build: construir localmente (`uv run build.py`) o desde un fork sigue produciendo un `.exe` sin firmar, igual que hoy.
- El job `build-linux` no cambia: Authenticode es exclusivo de Windows.
- El README documenta, a alto nivel, que el `.exe` oficial va firmado con un certificado autofirmado de Telconet y que el aviso de SmartScreen puede seguir apareciendo fuera de la red de la empresa.
- **No** se automatiza la generación del certificado ni su distribución por GPO: quedan fuera de este repositorio, a cargo de IT.

## Capabilities

### New Capabilities

- `executable-signing`: qué certifica el `.exe` de Windows publicado, cómo se firma en el pipeline (herramienta, algoritmo, sellado de tiempo), dónde vive el secreto que lo hace posible, y qué pasa cuando ese secreto falta o la firma falla.

### Modified Capabilities

<!-- Ninguna existente: no hay spec de `release-pipeline` ni `release-artifacts` archivada en openspec/specs/ todavía (el cambio que los introdujo, add-release-pipeline, sigue sin archivar), así que la firma se documenta como capability nueva en vez de delta sobre una spec inexistente. -->

## Impact

- **Pipeline**: `.github/workflows/release.yml`, job `build-windows` — un paso nuevo después de "Construir el ejecutable". No cambia disparadores, permisos de job existentes ni el resto de jobs.
- **Secretos del repositorio**: dos secretos nuevos de GitHub Actions (PFX en base64 y su contraseña), gestionados por quien administre el repositorio; no se añade código que los genere.
- **Builds locales y forks**: sin cambio de comportamiento cuando no hay secreto configurado.
- **Fuera de este repositorio**: generación del certificado autofirmado y su distribución como raíz de confianza por GPO — responsabilidad de IT/el usuario, documentada aquí solo como referencia.
