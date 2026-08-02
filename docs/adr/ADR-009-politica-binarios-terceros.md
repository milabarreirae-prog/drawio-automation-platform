# ADR-009: Política de binarios de terceros en el árbol versionado

**Date**: 2026-08-02
**Status**: DECIDIDA
**Decisión**: Los binarios de terceros (SDKs propietarios, wheels precompiladas, imágenes
de kernel, librerías compartidas `.so`, PDFs de documentación técnica, etc.) **NO van a
git**. El mecanismo default para incorporar un binario de terceros es
**descarga-en-build con verificación de hash** (SHA-256 fijado en el manifiesto de
build, al estilo Maven/Gradle/PyPI/npm). Si descarga-en-build no es viable —CI air-gapped,
entorno offline, dependencia de red no confiable—, entonces **almacenamiento de
artefactos dedicado** con propietario explícito. Git no es un almacén de artefactos.
**Alternativas evaluadas**:
- **(1) Binarios en git** — *rechazada*: el blob es irreversible en la práctica (una vez
  pusheado, la reescritura de historia requiere coordinación de todos los clones); no
  hay evidencia de revisión de licencia de redistribución para los binarios ya
  commitados en otra célula (ver *Alcance honesto* abajo); hincha el `.git` de todos
  los clones para siempre.
- **(2) Almacenamiento de artefactos dedicado** (registro de paquetes, bucket S3,
  GitHub Releases, Artifactory) — *aceptada como fallback* cuando descarga-en-build no
  es viable. Requiere propietario explícito (célula o persona) y política de retención.
- **(3) Descarga-en-build con hash SHA-256 fijado** — *DECIDIDA como default*. El
  manifiesto de build (Dockerfile, `requirements.txt` con hashes, `package.json` con
  `integrity`, script de setup) declara el hash; si el artifact bajado no matchea, el
  build falla. Reproducible, auditable, sin binarios en el repo.

**Contexto**: Barrido retroactivo de `lider-arquitectura-transversal`
(2026-08-02, ver `/d/atahualpa-dev/scratch/.hive/exchange/ColmenaOS/lider-arquitectura-instruccion-barrido-retroactivo-2026-08-02.md`):
~90 MB de binarios de terceros agregados al árbol versionado en 3 días en otra célula
de la colmena (Rockchip SDK: PDFs de documentación, wheels propietarias, imágenes de
kernel, `librknnrt.so`). Según la instrucción, el `.git` de esa célula ya pesa ~87 MB.
No hay evidencia en el barrido de revisión de licencia de redistribución para el SDK
propietario de Rockchip. Esta célula (`drawio-automation-platform`) **no tiene
binarios de terceros en su árbol** — verificación en vivo:

```
$ find . -type f \( -name "*.pdf" -o -name "*.whl" -o -name "*.so" -o -name "*.img" -o -name "*.bin" \)
(sin resultados)
```

Este ADR es **política prospectiva** para esta célula y **guía de política colmena-wide**.
La verificación de licencia de los binarios Rockchip ya commitados es responsabilidad
de la célula que los commitó — ver *Alcance honesto*.

**Consecuencias**:
- **PR gate**: todo PR que introduzca un binario de terceros debe traer (a) hash
  SHA-256 fijado en el manifiesto de build, y (b) justificación escrita de licencia de
  redistribución en la descripción del PR o en un archivo `LICENSES.third-party` junto
  al binario. Sin esos dos campos, el PR no se mergea.
- **.gitignore**: esta célula mantiene patrones que excluyen binarios comunes del
  árbol. `.gitignore` actual ya cubre `*.pdf`, `*.svg`, `*.png` (con excepciones
  controladas en `tests/expected/`). Se agregan como nota de vigilancia los patrones
  `*.whl`, `*.so`, `*.img`, `*.bin` — si algún dependency futura los requiere, la
  excepción se documenta en el mismo PR que la introduce.
- **Remoción de binarios ya versionados**: si un binario de terceros ya está en git,
  su remoción requiere reescritura de historia (`git filter-repo` / `BFG`). Esta
  célula **no toma esa decisión sola**: la reescritura afecta a todos los clones y
  requiere coordinación con las células afectadas y con `lider-arquitectura-transversal`.
  Este ADR no ejecuta remoción — solo establece la política hacia adelante.
- **Descarga-en-build**: los Dockerfiles y scripts de setup de esta célula que
  requieran artifacts de terceros los declaran con hash SHA-256 y URL fija. Si la URL
  deja de responder, el build falla con mensaje claro (no se "degrada" a binario
  random de internet).
- **Cross-reference**: este ADR converge con **ADR-008** (higiene de artifacts: el
  compose base no lleva credenciales ni puertos publicados, los overrides dev/prod
  separan lo que se versiona de lo que no) y con **Ax-C4N-001** (fidelidad > belleza:
  el motor no inventa; la documentación de licencias tampoco — si no puedo verificar
  una licencia en vivo, la roto *por validar* en lugar de afirmarla).

---

### Alcance honesto

- **Peso del `.git` de otras células**: citamos "~87 MB" según la instrucción de
  `lider-arquitectura-transversal` del 2026-08-02. Esta célula no auditó ese `.git`
  de forma independiente — no lo afirmamos como dato verificado por nosotros.
- **Licencias del Rockchip SDK**: no verificamos en vivo las licencias de los
  binarios Rockchip (PDFs, wheels, `librknnrt.so`, imágenes de kernel). La
  verificación de redistribución es responsabilidad de la célula que los commitó;
  esta célula sólo establece la política prospectiva y la guía colmena-wide.
- **Ejecución de remoción**: la limpieza de binarios ya versionados en otras células
  **no la ejecuta esta célula**. Este ADR es política; la ejecución requiere acuerdo
  de las células afectadas y de `lider-arquitectura-transversal`.

---

> **Nota de uso:** Copiar este archivo para políticas futuras de artifacts. Si un hecho
> no puede verificarse en vivo, rotularlo *por validar* (Ax-C4N-001: el motor no
> inventa; la documentación de licencias tampoco).
