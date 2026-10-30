## 1. Preparación (fuera del pipeline)

- [ ] 1.1 Generar el certificado autofirmado de firma de código (`New-SelfSignedCertificate` con EKU `1.3.6.1.5.5.7.3.3`, `-Type CodeSigningCert`) y exportarlo a `.pfx` con contraseña.
- [ ] 1.2 Codificar el `.pfx` en base64 y crear los secretos del repositorio `WINDOWS_CODESIGN_PFX_BASE64` y `WINDOWS_CODESIGN_PFX_PASSWORD`.
- [ ] 1.3 Exportar el certificado público (`.cer`, sin clave privada) para que IT lo distribuya luego como raíz de confianza vía GPO (paso manual, fuera de este repositorio y de este checklist).

## 2. Workflow de release

- [x] 2.1 Añadir el step de firma al job `build-windows` en `.github/workflows/release.yml`, después de "Comprobar que existe" y antes de `actions/upload-artifact`, condicionado a `if: ${{ secrets.WINDOWS_CODESIGN_PFX_BASE64 != '' }}`.
- [x] 2.2 Dentro del step: decodificar `WINDOWS_CODESIGN_PFX_BASE64` a un `.pfx` temporal en el workspace del runner, invocar `signtool sign /f <pfx> /p <password> /fd SHA256 /tr <TSA publica> /td SHA256 dist\pr-watch.exe`, y borrar el `.pfx` temporal al final del step (en éxito y en fallo).
- [x] 2.3 Añadir un paso de verificación tras la firma que confirme con `Get-AuthenticodeSignature` que `dist\pr-watch.exe` quedó firmado (`Status -ne 'NotSigned'`), y que falle el job si no es así.
- [x] 2.4 Confirmar que el job `build-linux` queda intacto (ningún cambio).

## 3. Documentación

- [x] 3.1 Añadir al README una nota breve: el `.exe` oficial se firma con un certificado autofirmado de Telconet; el nombre de editor aparece en Propiedades, pero el aviso de SmartScreen puede seguir apareciendo fuera de la red de la empresa hasta que se distribuya el certificado por GPO (responsabilidad de IT).
- [x] 3.2 Documentar en el README (o en un archivo aparte referenciado desde ahí) el comando de referencia de la tarea 1.1, para que generar o rotar el certificado no dependa de reconstruir el procedimiento desde cero.

## 4. Verificación

- [ ] 4.1 Con los secretos configurados, disparar el workflow (push a `main` o re-run manual) y confirmar en los logs que el step de firma corrió, `signtool` terminó en éxito y la verificación posterior pasó.
- [ ] 4.2 Descargar el artefacto `pr-watch-windows` de esa ejecución y comprobar localmente con `Get-AuthenticodeSignature` que el binario está firmado y lleva sello de tiempo.
- [ ] 4.3 Confirmar que, sin los secretos configurados (por ejemplo simulando la condición o revisando un run anterior a este cambio), el job sigue completando y publicando el `.exe` sin firmar, sin marcar el job como fallido.
- [x] 4.4 `ruff check`, `ruff format --check` y `pyright` no aplican a este cambio (solo toca YAML y README), pero confirmar que `uv run python -m unittest discover -s tests` sigue en verde tras el cambio, por si algo en `tests/` depende indirectamente del workflow (p. ej. `test_release_version.py`).
