# Fork Setup Guide

Esta guía te ayuda a configurar el fork correctamente **antes** de usar GitHub Copilot.

## Prerequisitos

- Cuenta de GitHub
- Git instalado localmente
- Permisos para crear repositorios en tu organización

## Paso 1: Crear el Fork en GitHub

1. Ve a https://github.com/rlespinasse/drawio-desktop-headless
2. Haz clic en el botón **"Fork"** (esquina superior derecha)
3. Selecciona tu organización o cuenta personal
4. **Nombre del repositorio:** `drawio-automation-platform`
5. **Descripción:** "Enterprise Draw.io automation platform with API, async rendering, and compliance validation"
6. **Copia solo la rama main:** ✅ (recomendado)
7. Haz clic en **"Create fork"**

## Paso 2: Clonar Localmente

```bash
# Clonar tu fork
git clone https://github.com/TU_USUARIO/drawio-automation-platform.git
cd drawio-automation-platform
```

## Paso 3: Configurar Remotes

```bash
# Agregar el repositorio original como "upstream"
git remote add upstream https://github.com/rlespinasse/drawio-desktop-headless.git

# Verificar configuración
git remote -v
```

Deberías ver:
```
origin    https://github.com/TU_USUARIO/drawio-automation-platform.git (fetch)
origin    https://github.com/TU_USUARIO/drawio-automation-platform.git (push)
upstream  https://github.com/rlespinasse/drawio-desktop-headless.git (fetch)
upstream  https://github.com/rlespinasse/drawio-desktop-headless.git (push)
```

## Paso 4: Sincronizar con Upstream

```bash
# Obtener última versión del upstream
git fetch upstream

# Crear rama de desarrollo basada en upstream
git checkout -b develop upstream/main
```

## Paso 5: Crear Commit Inicial de Fork

```bash
# Crear commit vacío que documente el fork
git commit --allow-empty -m "chore: fork initialization from rlespinasse/drawio-desktop-headless

Forked from: https://github.com/rlespinasse/drawio-desktop-headless
Commit: $(git rev-parse upstream/main)
Date: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

This fork adds:
- FastAPI REST API for diagram generation
- ARQ async task queue for rendering
- Corporate compliance validation
- Enterprise stencil support (AWS, GCP, Azure, ArchiMate, C4, Cisco, OCI)
- S3/MinIO storage integration
- Webhook callback system

See FORK.md for detailed differences."
```

## Paso 6: Push a Tu Fork

```bash
# Push rama develop
git push origin develop

# Crear y push rama main
git checkout -b main
git push origin main
```

## Paso 7: Inicializar Estructura de Directorios

```bash
# Hacer el script ejecutable
chmod +x scripts/init_fork.sh

# Ejecutar inicialización
./scripts/init_fork.sh
```

Este script creará:
- Estructura de directorios (api/, worker/, scripts/, etc.)
- Archivos base vacíos
- .gitignore configurado
- .env.example con variables documentadas
- FORK.md con información del punto de divergencia

## Paso 8: Commit Inicial de Estructura

```bash
git add .
git commit -m "chore: initialize project structure

- Created directory structure for API, worker, scripts
- Added .gitignore and .env.example
- Generated FORK.md with upstream attribution
- Prepared for code generation via GitHub Copilot"

git push origin main
```

## Paso 9: Verificar Configuración

```bash
# Verificar remotes
git remote -v

# Verificar ramas
git branch -a

# Verificar último commit
git log --oneline -n 5
```

Deberías ver:
```
* abc1234 (HEAD -> main, origin/main) chore: initialize project structure
* def5678 chore: fork initialization from rlespinasse/drawio-desktop-headless
* ghi9012 (upstream/main) Latest upstream commit...
```

## ✅ Listo para Usar Copilot

Ahora puedes:
1. Abrir el proyecto en tu IDE (VS Code, Cursor, etc.)
2. Copiar el **Mega-Prompt v3.0** (con la FASE 0 incluida)
3. Pegarlo en GitHub Copilot Chat / Agent Mode
4. Dejar que genere el código sobre esta base correctamente estructurada

## Sincronización Futura con Upstream

Para mantener tu fork actualizado con cambios del upstream:

```bash
# Semanalmente o cuando haya releases importantes
git fetch upstream
git checkout main
git merge upstream/main

# Si hay conflictos, resolverlos
# Luego:
git push origin main
```

O usar el workflow automatizado `.github/workflows/upstream-sync.yml` que creará PRs automáticamente.

## Problemas Comunes

### Error: "fatal: 'upstream' does not appear to be a git repository"
**Solución:** Ejecuta `git remote add upstream https://github.com/rlespinasse/drawio-desktop-headless.git`

### Error: "Permission denied (publickey)"
**Solución:** Configura SSH keys o usa HTTPS con token:
```bash
git remote set-url origin https://TU_TOKEN@github.com/TU_USUARIO/drawio-automation-platform.git
```

### El script init_fork.sh falla
**Solución:** Verifica que estás en la raíz del repositorio y que `.git/` existe:
```bash
ls -la .git/