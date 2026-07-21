#!/usr/bin/env bash
# ============================================================================
# TITO Docker — One-shot build & setup
# ============================================================================
# This script:
#   1. Builds the EF5 container (ef5-container:latest)
#   2. Builds the TITO container (tito:latest)
#
# Usage:
#   ./docker-build.sh
#   ./docker-build.sh --no-ef5    # skip EF5 build (if already built)
#   ./docker-build.sh --no-cache  # force full rebuild
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_EF5=true
NO_CACHE=""

for arg in "$@"; do
    case "$arg" in
        --no-ef5) BUILD_EF5=false ;;
        --no-cache) NO_CACHE="--no-cache" ;;
    esac
done

echo "=============================================="
echo "  TITO Docker Build"
echo "=============================================="
echo "  Project root: $SCRIPT_DIR"
echo "  Build EF5:   $BUILD_EF5"
echo "  No cache:    ${NO_CACHE:-false}"
echo "=============================================="

# ── Step 1: Build EF5 container ────────────────────────────────────────────
if $BUILD_EF5; then
    echo ""
    echo ">>> STEP 1: Building EF5 container (ef5-container:latest) ..."
    cd "$SCRIPT_DIR/EF5/docker"
    docker build $NO_CACHE -t ef5-container:latest .
    cd "$SCRIPT_DIR"
    echo ">>> EF5 container built successfully."
else
    echo ""
    echo ">>> STEP 1: Skipping EF5 container build (--no-ef5)."
fi

# ── Step 2: Build TITO container ───────────────────────────────────────────
echo ""
echo ">>> STEP 2: Building TITO container (tito:latest) ..."
echo "    This will take 10-20 min (downloading conda packages, PyTorch, etc.)"
docker build $NO_CACHE -t tito:latest .
echo ">>> TITO container built successfully."

# ── Done ───────────────────────────────────────────────────────────────────
echo ""
echo "=============================================="
echo "  Build complete!"
echo "=============================================="
echo ""
echo "  Images:"
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | grep -E "ef5-container|tito" || true
echo ""
echo "  Quick start:"
echo "    # Interactive shell"
echo "    docker-compose run --rm tito shell"
echo ""
echo "    # Operational run"
echo "    docker-compose run --rm tito operational"
echo ""
echo "    # Hindcast run"
echo '    docker-compose run --rm tito hindcast "2025-11-16 00:00" "2025-11-17 20:00"'
echo ""
