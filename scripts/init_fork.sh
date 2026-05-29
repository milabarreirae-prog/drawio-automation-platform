#!/bin/bash
# scripts/init_fork.sh
# Inicializa la estructura de directorios para el fork de drawio-automation-platform

set -e

echo "🚀 Inicializando estructura de drawio-automation-platform..."

# Verificar que estamos en un repositorio Git
if [ ! -d ".git" ]; then
    echo "❌ Error: Este directorio no es un repositorio Git"
    echo "   Ejecuta primero: git clone <tu-fork>"
    exit 1
fi

# Verificar que upstream está configurado
if ! git remote | grep -q "^upstream$"; then
    echo "❌ Error: Remote 'upstream' no está configurado"
    echo "   Ejecuta: git remote add upstream https://github.com/rlespinasse/docker-drawio-desktop-headless.git"
    exit 1
fi

# Crear estructura de directorios
echo "📁 Creando estructura de directorios..."
mkdir -p api worker scripts stencils/downloaded docker tests .github/workflows docs examples

# Crear archivos base vacíos (Copilot los llenará)
echo "📄 Creando archivos base..."

# Archivos raíz
touch LICENSE NOTICE FORK.md THIRD_PARTY_LICENSES.md README.md ARCHITECTURE.md
touch .gitignore .env.example .dockerignore pyproject.toml

# API
touch api/__init__.py api/main.py api/config.py api/schemas.py api/linting.py api/requirements.txt

# Worker
touch worker/__init__.py worker/tasks.py worker/stencils_loader.py worker/models.py
touch worker/s3_uploader.py worker/webhooks.py worker/requirements.txt

# Scripts
touch scripts/fetch_stencils.py scripts/verify_licenses.py scripts/upstream_sync.sh
chmod +x scripts/upstream_sync.sh

# Stencils
echo '{"version": "1.0.0", "stencils": {}}' > stencils/manifest.json

# Docker
touch docker/Dockerfile.api docker/Dockerfile.worker docker/docker-compose.yml docker/worker-entrypoint.sh
chmod +x docker/worker-entrypoint.sh

# Tests
touch tests/__init__.py tests/test_linting.py tests/test_stencils_loader.py tests/test_api.py

# GitHub Workflows
touch .github/workflows/ci.yml .github/workflows/release.yml
touch .github/workflows/stencils-update.yml .github/workflows/upstream-sync.yml

# Crear .gitignore básico
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/
.venv
*.egg-info/
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Docker
.dockerignore

# Environment
.env
.env.local
.env.*.local

# Stencils descargados (demasiado grandes para GitHub)
stencils/downloaded/*.xml
stencils/downloaded/*.metadata.json
!stencils/downloaded/.gitkeep

# Logs
*.log
logs/

# Temporary
*.tmp
*.bak
*.cache
.DS_Store
EOF

# Crear .gitkeep para directorios vacíos
touch stencils/downloaded/.gitkeep
touch tests/.gitkeep

# Crear .env.example
cat > .env.example << 'EOF'
# ============================================================================
# Redis Configuration
# ============================================================================
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_HOST_PORT=6380

# ============================================================================
# S3/MinIO Storage Configuration
# ============================================================================
# Para MinIO local (desarrollo):
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=drawio-exports

# Para AWS S3 (producción):
# S3_ENDPOINT_URL=
# S3_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
# S3_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
# S3_BUCKET_NAME=your-drawio-exports-bucket
# S3_REGION=us-east-1

# ============================================================================
# Stencils Configuration
# ============================================================================
ALLOWED_STENCILS=aws4,gcp2,azure,archimate3,c4,cisco,oci

# ArchiMate License (requerido para uso comercial)
# Obtener en: https://www.opengroup.org/certifications/archimate
ARCHIMATE_LICENSE_KEY=

# ============================================================================
# Worker Configuration
# ============================================================================
WORKER_MAX_JOBS=3
WORKER_JOB_TIMEOUT=300

# ============================================================================
# Logging
# ============================================================================
LOG_LEVEL=info
EOF

# Crear FORK.md inicial
UPSTREAM_COMMIT=$(git rev-parse upstream/v1.x 2>/dev/null || echo "unknown")
UPSTREAM_DATE=$(git log -1 --format=%cd upstream/v1.x 2>/dev/null || echo "unknown")

cat > FORK.md << EOF
# Fork Declaration: drawio-automation-platform

## Origin

This project is a fork of [rlespinasse/docker-drawio-desktop-headless](https://github.com/rlespinasse/docker-drawio-desktop-headless).

**Fork Point:**
- **Upstream Commit:** \`${UPSTREAM_COMMIT}\`
- **Upstream Date:** ${UPSTREAM_DATE}
- **Fork Date:** $(date -u +"%Y-%m-%dT%H:%M:%SZ")

## Why This Fork?

The original project provides an excellent Docker image for running Draw.io Desktop in headless mode. However, our use case required:

1. **REST API Layer**: Programmatic access via HTTP endpoints
2. **Async Task Queue**: Non-blocking rendering with ARQ + Redis
3. **Corporate Compliance**: Validation of colors, stencils, and licenses
4. **Enterprise Stencils**: Native support for AWS, GCP, Azure, ArchiMate, C4, Cisco, OCI
5. **Storage Integration**: S3/MinIO upload and webhook callbacks
6. **Multi-tenant Architecture**: Isolated workers with resource limits

These features are out of scope for the original project, which focuses on providing a minimal headless Docker image.

## Key Differences

| Feature | Upstream | This Fork |
|---------|----------|-----------|
| Docker Image | ✅ Standalone | ✅ Base image + API layer |
| REST API | ❌ | ✅ FastAPI |
| Async Queue | ❌ | ✅ ARQ + Redis |
| XML Validation | ❌ | ✅ lxml + corporate policies |
| Enterprise Stencils | ⚠️ Manual | ✅ Auto-detection + caching |
| S3 Integration | ❌ | ✅ boto3 |
| Webhooks | ❌ | ✅ httpx async |
| License Compliance | ❌ | ✅ ArchiMate validation |

## Upstream-First Policy

We are committed to contributing back to the upstream project whenever possible:

1. **Bug Fixes**: Any bugs found in the base Docker image will be reported upstream
2. **Security Patches**: Security improvements will be submitted as PRs
3. **Documentation**: Improvements to README/examples will be shared
4. **Feature Scope**: Features specific to our use case (API, queue, validation) will remain in this fork

### How We Sync with Upstream

\`\`\`bash
# Weekly sync via GitHub Actions
git fetch upstream
git merge upstream/v1.x
# Resolve conflicts if any
# Run tests
# Push to fork
\`\`\`

See \`.github/workflows/upstream-sync.yml\` for automation details.

## Acknowledgments

We gratefully acknowledge the work of [rlespinasse](https://github.com/rlespinasse) and contributors for maintaining the upstream project. This fork would not be possible without their foundational work.

## Contact

- **Upstream Issues**: https://github.com/rlespinasse/docker-drawio-desktop-headless/issues
- **Fork Issues**: https://github.com/YOUR_ORG/drawio-automation-platform/issues
- **Upstream Discussions**: Use GitHub Discussions in the upstream repo

## License Compliance

This fork complies with the MIT License of the upstream project:
- Original copyright notices preserved in \`NOTICE\`
- License text included in \`LICENSE\`
- Modifications clearly documented in commit history
- Fork relationship declared in this file

EOF

echo "✅ Estructura inicializada correctamente"
echo ""
echo "📋 Próximos pasos:"
echo "   1. Copia el Mega-Prompt v3.0 en tu IDE con Copilot"
echo "   2. Pega el prompt y deja que genere el código"
echo "   3. Ejecuta: git add . && git commit -m 'feat: initial implementation'"
echo "   4. Ejecuta: git push origin main"
echo ""
echo "🔗 Repositorio listo para desarrollo"