## Idioma

- Responder siempre en español.

## OpenSpec

- **Para trabajo dirigido por especificación, usar OpenSpec, no las skills de superpowers.** Si una skill de superpowers (`brainstorming`, `writing-plans`, `subagent-driven-development`, `executing-plans`) pide otra ruta u otro formato, gana OpenSpec.
- Los artefactos van en `openspec/changes/<nombre>/` — `proposal.md`, `design.md`, `tasks.md` y los deltas en `specs/` —, nunca en `docs/superpowers/`. El `tasks.md` sigue el formato de OpenSpec (`## N. Grupo` con ítems `- [ ] N.M`).
- **Implementar directo.** No usar el ciclo de subagente por tarea más revisión de `subagent-driven-development` salvo que el usuario lo pida explícitamente: para cambios de este tamaño cuesta más de lo que aporta.
- **Al aplicar un cambio de OpenSpec (`/opsx:apply`), crear siempre una rama nueva a partir de `master` actualizado.** No implementar sobre `master`.
- Flujo (el mismo de `/nueva-rama`):

  ```bash
  git checkout master
  git pull origin master
  git checkout -b <prefijo>/<3-5-palabras> --no-track
  ```

- La rama nueva **no debe quedar con upstream a `master`**: crearla con `--no-track`. El nombre sigue las convenciones de `/nueva-rama` (prefijo de Conventional Commits + 3 a 5 palabras).

## Commit Policy

- No hacer commit por cada cambio individual. Agrupar cambios relacionados en un solo commit.
- **Solo hacer commit cuando el usuario lo solicite explícitamente.** No commitear de forma proactiva al terminar una tarea.
- No agregar `Co-Authored-By: Claude` ni ningún otro coautor automático en los mensajes de commit.
- El hook `commit-msg` de `.githooks/` quita esos trailers del mensaje automáticamente. En un clon nuevo hay que activarlo una vez: `git config core.hooksPath .githooks`.
