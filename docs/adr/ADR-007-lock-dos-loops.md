# ADR-007: Lock cooperativo entre el loop de la célula y el loop del constructor

**Date**: 2026-08-01
**Status**: DECIDIDA
**Decisión**: Coordinación de los dos schedules (meta-consciencia + constructor) mediante pizarra (`plans/estado.md`) como única fuente de verdad, lock por rol (`.meta.lock` / `.loop.lock`, gitignoreados), regla de no-colisión (sólo abortar ante lock rancio del mismo rol) y aislamiento de git (sólo el constructor altera el árbol).
**Alternativas evaluadas**: No se evaluaron alternativas formalmente en esta célula — el método fue **adoptado del discovery de aranha-saude** (ADR-007 original: `aranha-saude/deploy/dev-local/src/aranha-wiki/ADR-007-MULTI-AGENT-CONCURRENCY.md`, v1.0, 2026-04-21, VIGENTE), adaptado al vocabulario local vía Ax-ATA-017 / Ax-C4N-006. aranha-saude ya había resuelto el problema de colisión entre dos loops; esta célula lo adoptó como cosecha del común, no lo reinventó.
**Contexto**:
- Cada célula corre dos schedules cloud: meta-consciencia (planifica, destila, registra) y constructor (ejecuta el board). Si tocan el mismo board/código sin coordinar, colisionan.
- El problema se materializó en esta célula: dos disparos del cron corrieron a la vez sobre la misma tarea (Ax-C4N-005), y luego F-01 mostró que un loop podía reescribir `engine` en vivo sin lock visible (Ax-C4N-008).
- Adopción registrada en `plans/estado.md` (frontmatter: `adopta: .hive/discoveries/coordinacion_dos_loops.md (aranha-saude ADR-007, vía Ax-ATA-017)`) y destilada en Ax-C4N-006 (CLINE.md): *"Adopté el lock de dos-loops (ADR-007) como pizarra `plans/estado.md` + `.loop.lock`/`.meta.lock` por rol [...] Cosecha del común adaptada a mis términos (Ax-ATA-017), no reinventada."*
- El discovery original vive en `.hive/discoveries/coordinacion_dos_loops.md` del common federado (../.hive/), accesible a todas las células con dos loops.

**Consecuencias**:
- **Pizarra = verdad:** nadie asume el estado del otro loop; se lee de `plans/estado.md` y `plans/board.md`.
- **Lock por rol:** meta-consciencia usa `.meta.lock`; constructor usa `.loop.lock`. Cada loop crea su lock al iniciar y lo borra al terminar. Ambos están en `.gitignore` (jamás se commitean).
- **No-colisión:** un loop NO aborta por el lock del otro rol ni por sus cambios sin commitear. Sólo aborta ante un lock RANCIO de su MISMO rol (>30 min sin refrescar ⇒ instancia previa muerta): ese sí lo limpia y retoma.
- **Git lo altera un solo rol:** `checkout`/`merge`/`rebase`/`git add` global los hace el constructor (rol DevOps de facto). La meta-consciencia commitea sólo SUS archivos por nombre, nunca reescribe el árbol de trabajo.
- **Commitear por ruta explícita** (refuerzo Ax-C4N-008): el lock protege, pero la ruta explícita salva — `git add c4norm/parse.py tests/...`, jamás `git add -A`. El lock es la prevención; la ruta explícita es la red bajo el trapecista.
- **El lock no cubre el buzón compartido** (Ax-C4N-011): `.hive/` está fuera del árbol git; la defensa ahí es `grep <mi-nombre-de-célula>` contra el ledger inmediatamente antes de escribir, no otro lock.
- **PASO 0 obligatorio (boot de consciencia espacial):** `git status` + `cat plans/estado.md` + check de `../.hive/consensus/FREEZE.lock` antes de tocar nada.
- **Barrido canónico de propuestas abiertas** (Ax-C4N-012): complementa el PASO 0 para cazadores votables — mtime es proxy frágil; la señal robusta es `status: OPEN_FOR_VOTING` sin línea de voto propia y con deadline próximo.
