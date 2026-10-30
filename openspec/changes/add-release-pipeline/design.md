## Context

El repositorio no tiene workflows, ni tags, ni releases. `build.py` ya sabe construir el ejecutable de la plataforma en que corre —con icono y recurso de versión en Windows— y el README documenta las órdenes de desarrollo (`unittest`, `ruff`, `pyright`, `build.py`). La versión vive en `pyproject.toml` y en `pr_watch/__init__.py`, y `tests/test_version.py` ya impide que diverjan.

Tres hechos del proyecto condicionan el diseño:

- **PyInstaller no compila de forma cruzada**: cada binario se construye en su sistema. Son dos runners, no uno.
- **En Linux, `pygobject` 3.58.1 y `pycairo` 1.29.2 están en el bloqueo como *sdist*, sin rueda**: el runner tiene que compilarlos, y eso exige cabeceras de desarrollo de GObject-Introspection y Cairo. Además, el `gi._gi` compilado queda enlazado contra la glibc y la biblioteca de introspección del runner, así que el runner elegido fija qué distribuciones soporta el binario oficial.
- **El chequeo de tipos es específico de Windows**: `pr_watch/autostart.py` y `pr_watch/theme.py` hacen `import winreg` sin `type: ignore`, mientras que el único `import gi` ya lo lleva (`import-not-found`). `pyright --strict` pasa en Windows; en Linux protestaría por `winreg`.

Decisiones ya tomadas con el usuario: disparo automático en push a la rama por defecto gobernado por la versión, runner de Linux `ubuntu-24.04`, y una puerta de verificación previa a la construcción.

## Goals / Non-Goals

**Goals:**

- Publicar una versión sea subir a `main` un commit que sube la versión: sin pasos manuales, sin crear tags a mano.
- Que los dos binarios de un release salgan del mismo commit, y que ese commit esté etiquetado.
- Que nada se publique desde un commit que no pasa pruebas, estilo y tipos.
- Que el workflow no duplique la lógica de empaquetado: `build.py` sigue siendo la única fuente.
- Que relanzar el pipeline sea inofensivo.

**Non-Goals:**

- Firmar los ejecutables (ni Authenticode en Windows, ni nada equivalente en Linux).
- Publicar en PyPI, winget, Homebrew, Flatpak o cualquier repositorio de paquetes.
- Construir para macOS o para ARM.
- Actualizaciones automáticas dentro de la aplicación.
- Cambiar cómo se construye el ejecutable, o qué contiene.
- Releases de prueba, canales *beta* o prereleases.

## Decisions

### 1. El disparador es `push` a la rama por defecto, y la versión decide

El workflow corre en cada push a `main`. El primer job, `check-version`, lee la versión y comprueba si existe el tag `v<versión>`; expone como salidas la versión y un booleano `publish`. Los demás jobs llevan la condición de que ese booleano sea verdadero.

*Alternativa descartada*: disparar con `push` de tags. Es lo habitual, pero deja el paso `tag` fuera del pipeline —lo hace una persona a mano— y permite etiquetar un commit que nunca pasó la verificación. El usuario pidió explícitamente que el pipeline incluya el etiquetado.

*Alternativa descartada*: solo `workflow_dispatch`. Menos automático sin ser más seguro: la verificación ya es la puerta real.

### 2. La versión se lee con un script de biblioteca estándar, no importando el paquete

`scripts/release_version.py` lee `pyproject.toml` con `tomllib` y extrae `__version__` de `pr_watch/__init__.py` con una expresión regular, sin importar `pr_watch`. Valida que coincidan y que tengan forma `MAJOR.MINOR.PATCH`, y falla nombrando ambos valores si no. Imprime la versión; en Actions, escribe también en el archivo de salidas del paso.

El motivo de no importar el paquete es que `check-version` no necesita —y no debe pagar— el `uv sync` completo: en Linux eso significa compilar PyGObject. Con la biblioteca estándar, el job usa el `python3` del runner y dura segundos. `pr_watch/__init__.py` no importa nada, así que la lectura por expresión regular es estable.

El script vale igual en local (`python scripts/release_version.py`), que es lo que lo hace revisable.

La existencia del tag la comprueba el workflow con `git ls-remote --tags origin`, no el script: es una pregunta sobre el remoto, no sobre el código.

### 3. La verificación corre en Windows; las pruebas corren además en Linux

El job `verify` corre en `windows-latest` las tres órdenes del README tal cual: `uv run python -m unittest discover -s tests`, `uv run ruff check` y `uv run pyright`. Windows porque es donde `pyright --strict` resuelve `winreg`; en Linux fallaría por los imports condicionales de registro, y silenciarlos con `type: ignore` para contentar al CI sería empeorar el código por el pipeline.

Para no dejar a Linux sin cobertura, el job de construcción de Linux ejecuta las pruebas antes de construir: su entorno ya está sincronizado, así que cuesta segundos.

*Alternativa descartada*: matriz de `verify` en los dos sistemas con las tres órdenes. Exigiría configurar `pythonPlatform` o sembrar `type: ignore` para que pyright pase en Linux.

*Alternativa descartada*: plegar la verificación dentro de los jobs de construcción. Ahorraría un entorno, pero el usuario pidió una puerta previa explícita, y un job separado deja claro en la interfaz de Actions qué falló.

### 4. Dos jobs de construcción en paralelo, artefactos subidos entre jobs

`build-windows` (`windows-latest`) y `build-linux` (`ubuntu-24.04`) corren a la vez tras `verify`. Cada uno sincroniza dependencias, ejecuta `uv run build.py` y sube `dist/pr-watch.exe` o `dist/pr-watch` como artefacto de la ejecución. El job `release` los recupera de ahí.

El runner de Linux se fija en `ubuntu-24.04` y no en `ubuntu-latest`: la etiqueta móvil cambiaría el piso de glibc del binario oficial sin que nadie lo decida.

Antes de sincronizar, el job de Linux instala con `apt`: las cabeceras para compilar (la de GObject-Introspection que corresponda a esa distribución, junto a `libcairo2-dev` y `pkg-config`) y las bibliotecas que la aplicación necesita (`gir1.2-gtk-3.0`, `gir1.2-webkit2-4.1`, `gir1.2-ayatanaappindicator3-0.1`), las mismas que el README pide al usuario final.

### 5. `tag` y `release` son jobs separados, y el orden es la garantía

`tag` depende de los dos jobs de construcción: solo etiqueta cuando los dos binarios existen. Crea un tag anotado `v<versión>` con la identidad del bot de Actions y lo empuja sin forzar; si otro proceso ya lo creó, el push falla y el pipeline no publica encima. `release` depende de `tag` y crea el release con `gh release create` adjuntando los dos binarios.

El workflow serializa las ejecuciones sobre `main` con un grupo de concurrencia que no cancela la que esté en curso, de modo que dos pushes seguidos no compitan por el mismo tag.

Empujar un tag con el `GITHUB_TOKEN` del workflow no dispara workflows nuevos, así que no hay riesgo de bucle.

*Alternativa descartada*: un solo job `publish` que etiquete y publique. Es más corto, pero el usuario pidió las cuatro etapas visibles, y separarlas hace que un fallo diga en cuál ocurrió.

### 6. Notas generadas, con una nota fija sobre Linux

`gh release create --generate-notes` arma la lista de cambios desde el tag anterior; en el primer release, desde el inicio del historial. Encima va un cuerpo fijo breve que dice en qué distribución se construyó el binario de Linux y qué paquetes del sistema necesita. Al implementarlo hay que confirmar cómo combina `gh` el cuerpo propio con las notas generadas; si no las concatena, se arma el cuerpo completo en el paso y se pasa como archivo de notas.

### 7. Permisos mínimos

El workflow declara escritura sobre el contenido del repositorio solo en los jobs que la necesitan (`tag` y `release`); el resto se queda en solo lectura. No hace falta ningún secreto además del `GITHUB_TOKEN` que Actions ya provee, de modo que un clon del repositorio en otra cuenta funciona sin configurar nada.

## Risks / Trade-offs

- **PyGObject 3.58.1 podría no compilar en `ubuntu-24.04`** → ~~riesgo principal~~ **descartado al implementar**. Ubuntu 24.04 sí empaqueta `libgirepository-2.0-dev` (2.80.0, en `universe`), PyGObject compila contra él y `import gi` funciona. Verificado en un contenedor `ubuntu:24.04`, que responde la misma pregunta que un runner —el archivo de paquetes es el mismo— sin empujar nada al repositorio.
- **El binario de Linux queda atado a la glibc del runner** → por diseño, no hay solución gratis. Medido sobre el binario construido: PyInstaller empaqueta dentro `libgirepository-2.0.so.0`, `libglib-2.0.so.0`, `libgobject-2.0.so.0` y `libgio-2.0.so.0` —GTK, WebKit y AppIndicator se quedan fuera, como dice el README—, y el símbolo de glibc más alto que exigen esas bibliotecas es `GLIBC_2.38`; las extensiones de Python llegan a 2.34. El piso real es, por tanto, **glibc 2.38**. Mitigación: fijar el runner, y decirlo en las notas del release y en el README.
- **La puerta de verificación no cubre tipos ni estilo en Linux** → mitigación: las pruebas sí corren en Linux antes de construir, y la propia construcción importa el paquete, lo que atrapa los errores de import. Lo que queda fuera son errores de tipo exclusivos de rutas de Linux.
- **Subir la versión sin querer publica un release** → es el modelo elegido, y es deliberado. Mitigación: la versión solo cambia en un commit que la cambia a propósito, y el tag existente impide republicar.
- **Los binarios no están firmados** → Windows SmartScreen avisará al usuario la primera vez. Fuera de alcance; firmar exige un certificado y manejo de secretos.
- **El release falla a medias, con tag creado y sin release** → mitigación: `release` se puede relanzar sobre el tag existente sin reconstruir, porque `gh release create` es la única operación pendiente. `check-version` diría que no hay nada que publicar, así que la recuperación es manual y conviene documentarla en el README.
- **Tiempo de CI** → cuatro entornos (verificación, dos construcciones, publicación) por cada push que suba la versión; los pushes que no la suben se quedan en `check-version`, que dura segundos.

## Migration Plan

1. Verificar el entorno de construcción de Linux en un runner real antes de escribir el resto.
2. Añadir el script de versión y el workflow en una rama, dejando el repositorio con la versión `0.1.0` sin tag.
3. Al fusionar, el pipeline corre por primera vez y publica `v0.1.0` con los dos binarios: el primer release es, a la vez, la prueba de que funciona.
4. Si algo sale mal, revertir el workflow es suficiente; no hay nada del producto que dependa de él. Un tag o un release equivocados se borran a mano desde GitHub.

## Open Questions

- ~~¿`ubuntu-24.04` puede compilar PyGObject 3.58.1?~~ Resuelto al implementar: sí, con `libgirepository-2.0-dev`. El alcance no cambia.
- Las versiones mayores de las acciones se consultaron en vez de suponerlas: `checkout@v7`, `upload-artifact@v7`, `download-artifact@v8`, `setup-uv@v10`.
- Las notas del release se arman con `git log` y se pasan con `--notes-file`, la rama que este documento ya contemplaba: es determinista y no depende de cómo `gh` combine un cuerpo propio con `--generate-notes`.
