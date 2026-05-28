#!/bin/bash
# scripts/upstream_sync.sh
# Sincroniza el fork con cambios del upstream

set -e

echo "🔄 Sincronizando con upstream..."

# Verificar que upstream está configurado
if ! git remote | grep -q "^upstream$"; then
    echo "❌ Error: Remote 'upstream' no está configurado"
    echo "   Ejecuta: git remote add upstream https://github.com/rlespinasse/drawio-desktop-headless.git"
    exit 1
fi

# Obtener últimos cambios
echo "📥 Fetching upstream changes..."
git fetch upstream

# Verificar si hay nuevos commits
LOCAL_COMMIT=$(git rev-parse main)
UPSTREAM_COMMIT=$(git rev-parse upstream/main)

if [ "$LOCAL_COMMIT" = "$UPSTREAM_COMMIT" ]; then
    echo "✅ Ya estás actualizado con upstream"
    exit 0
fi

echo "📊 Nuevos commits encontrados:"
git log --oneline main..upstream/main

# Crear rama para el merge
BRANCH_NAME="automated/upstream-sync-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$BRANCH_NAME"

# Intentar merge
echo "🔀 Intentando merge..."
if git merge upstream/main --no-edit; then
    echo "✅ Merge exitoso"
    
    # Ejecutar tests si existen
    if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ]; then
        echo "🧪 Ejecutando tests..."
        if command -v pytest &> /dev/null; then
            pytest tests/ || {
                echo "⚠️ Tests fallaron, pero el merge continúa"
            }
        fi
    fi
    
    echo ""
    echo "✅ Sincronización completada"
    echo "📋 Próximos pasos:"
    echo "   1. Revisa los cambios: git diff main..$BRANCH_NAME"
    echo "   2. Si todo OK: git checkout main && git merge $BRANCH_NAME"
    echo "   3. Push: git push origin main"
    echo "   4. Crea PR en GitHub si prefieres revisión"
    
else
    echo "❌ Conflictos detectados"
    echo "📋 Archivos con conflictos:"
    git diff --name-only --diff-filter=U
    
    echo ""
    echo "🔧 Resolución manual requerida:"
    echo "   1. Resuelve conflictos en los archivos listados"
    echo "   2. git add <archivos-resueltos>"
    echo "   3. git commit"
    echo "   4. git push origin $BRANCH_NAME"
    echo "   5. Crea PR en GitHub"
    
    exit 1
fi