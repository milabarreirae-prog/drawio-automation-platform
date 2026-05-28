#!/bin/bash
# ============================================================================
# Worker Entrypoint Script
# ============================================================================
# Pre-flight checks before starting the ARQ worker:
#   1. Verify Redis connectivity
#   2. Check stencil availability
#   3. Validate environment variables
#   4. Configure Chromium flags
#   5. Start Xvfb if not already running
#
# Usage:
#   ENTRYPOINT ["/usr/local/bin/worker-entrypoint.sh"]
#   CMD ["arq", "worker.tasks.WorkerSettings", "--workers", "3"]
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_success() {
    echo -e "${GREEN}[OK]${NC}    $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC}  $(date '+%Y-%m-%d %H:%M:%S') $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') $*"
}

# ============================================================================
# Check 1: Redis Connectivity
# ============================================================================
check_redis() {
    local redis_host="${REDIS_HOST:-redis}"
    local redis_port="${REDIS_PORT:-6379}"
    local retries=10
    local wait_seconds=2

    log_info "Checking Redis connectivity at ${redis_host}:${redis_port}..."

    for i in $(seq 1 $retries); do
        if timeout 3 bash -c "echo PING | redis-cli -h '${redis_host}' -p '${redis_port}' 2>/dev/null" | grep -q "PONG"; then
            log_success "Redis is reachable at ${redis_host}:${redis_port}"
            return 0
        fi

        if [ $i -lt $retries ]; then
            log_warn "Redis not ready (attempt ${i}/${retries}), retrying in ${wait_seconds}s..."
            sleep $wait_seconds
        fi
    done

    log_error "Redis is NOT reachable after ${retries} attempts. Exiting."
    return 1
}

# ============================================================================
# Check 2: Stencil Availability
# ============================================================================
check_stencils() {
    local manifest_path="/app/stencils/manifest.json"
    local download_dir="/app/stencils/downloaded"

    log_info "Checking stencil availability..."

    if [ ! -f "$manifest_path" ]; then
        log_warn "Stencil manifest not found at ${manifest_path}"
        log_warn "Stencil resolution will fall back to placeholders or cached libraries."
        return 0
    fi

    # Count available stencil XML files
    local stencil_count=0
    if [ -d "$download_dir" ]; then
        stencil_count=$(find "$download_dir" -maxdepth 1 -name "*.xml" -type f | wc -l)
    fi

    if [ "$stencil_count" -gt 0 ]; then
        log_success "Found ${stencil_count} cached stencil file(s) in ${download_dir}"
    else
        log_warn "No cached stencil files found. Stencils will be resolved at runtime."
        log_warn "Consider running: python scripts/fetch_stencils.py"
    fi
}

# ============================================================================
# Check 3: Environment Variables
# ============================================================================
check_env() {
    log_info "Checking environment configuration..."

    # Required variables
    local required_vars=("REDIS_HOST" "REDIS_PORT")
    local missing_vars=()

    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            missing_vars+=("$var")
        fi
    done

    if [ ${#missing_vars[@]} -gt 0 ]; then
        log_warn "Missing environment variables: ${missing_vars[*]}"
        log_warn "Using defaults where applicable."
    fi

    # ArchiMate license check
    if [ -n "${ARCHIMATE_LICENSE_KEY:-}" ]; then
        log_success "ARCHIMATE_LICENSE_KEY is configured"
    else
        log_warn "ARCHIMATE_LICENSE_KEY is not set — ArchiMate rendering will be BLOCKED"
    fi

    # Allowed stencils
    if [ -n "${ALLOWED_STENCILS:-}" ]; then
        log_info "Allowed stencils: ${ALLOWED_STENCILS}"
    else
        log_info "ALLOWED_STENCILS not set — all stencils allowed by default"
    fi
}

# ============================================================================
# Check 4: Draw.io CLI
# ============================================================================
check_drawio() {
    local drawio_cli="${DRAWIO_CLI_PATH:-/opt/drawio/drawio}"

    if [ -f "$drawio_cli" ]; then
        log_success "Draw.io CLI found at ${drawio_cli}"
    else
        log_error "Draw.io CLI NOT found at ${drawio_cli}!"
        log_error "The worker container MUST include the drawio-desktop binary."
        return 1
    fi

    # Check Xvfb availability
    if command -v Xvfb &> /dev/null; then
        log_success "Xvfb is available"
    else
        log_error "Xvfb is NOT available — headless rendering requires Xvfb!"
        return 1
    fi
}

# ============================================================================
# Check 5: Chromium Flags
# ============================================================================
configure_chromium() {
    # Default Chromium flags for Docker
    export CHROMIUM_FLAGS="${CHROMIUM_FLAGS:---no-sandbox --disable-gpu --disable-dev-shm-usage --disable-setuid-sandbox --single-process}"

    log_info "Chromium flags: ${CHROMIUM_FLAGS}"
}

# ============================================================================
# Start Xvfb (if not already running)
# ============================================================================
ensure_xvfb() {
    if ! pgrep -x Xvfb > /dev/null 2>&1; then
        log_info "Starting Xvfb on :99..."
        Xvfb :99 -screen 0 1280x1024x24 -ac +extension RANDR &
        export DISPLAY=:99
        sleep 1
        log_success "Xvfb started (PID: $(pgrep Xvfb))"
    else
        log_info "Xvfb already running"
        export DISPLAY="${DISPLAY:-:99}"
    fi
}

# ============================================================================
# Main
# ============================================================================
main() {
    echo ""
    echo "================================================"
    echo "  drawio-automation-platform — Worker"
    echo "  $(date '+%Y-%m-%d %H:%M:%S UTC')"
    echo "================================================"
    echo ""

    # Run all checks
    check_env
    check_drawio || exit 1
    check_redis || exit 1
    check_stencils
    configure_chromium
    ensure_xvfb

    echo ""
    log_success "All pre-flight checks passed."
    echo ""

    # Execute the CMD (ARQ worker)
    log_info "Starting ARQ worker: $*"
    exec "$@"
}

main "$@"