#!/bin/bash
# Hourly operational TITO via Apptainer (or Docker).
#
# Resolutions are now configured inside Caribbean_Comoros_config.py:
#   region_resolution_map = {"Antigua": "30m"}
# One orchestrator invocation runs them in order and shares a single precip
# prep, so this script just launches TITO once. States/outputs stay split
# (antigua_30m); FIM runs at 30m.
#
# Usage: ./manage_cron.sh [install|remove|status|run]
#
# Apptainer needs tito.sif in this folder and EF5/bin/ef5.
# Cron has a tiny PATH — we prepend /usr/bin so `apptainer` is found.

# ── Operator knobs (edit these) ──────────────────────────────────────────
REGION="Antigua"
# docker | apptainer | singularity (env override wins, e.g. TITO_RUNTIME=apptainer)
TITO_RUNTIME="${TITO_RUNTIME:-docker}"
CRON_SCHEDULE="5 * * * *"
# ─────────────────────────────────────────────────────────────────────────
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TITO_RUN="$SCRIPT_DIR/tito-run.sh"
LOG_DIR="$SCRIPT_DIR/outputs/logs"
LOCK_FILE="$LOG_DIR/tito_cron.lock"
CRON_CMD="$CRON_SCHEDULE $SCRIPT_DIR/manage_cron.sh run"

tito_already_running() {
    if pgrep -af "tito-run.sh operational" 2>/dev/null | grep -qF "$SCRIPT_DIR"; then
        return 0
    fi
    if [ "$TITO_RUNTIME" = "docker" ] && command -v docker >/dev/null 2>&1; then
        if docker ps --format '{{.Command}} {{.Mounts}}' 2>/dev/null \
            | grep -qF "$SCRIPT_DIR"; then
            return 0
        fi
    fi
    if [ "$TITO_RUNTIME" = "apptainer" ] || [ "$TITO_RUNTIME" = "singularity" ]; then
        if pgrep -af "apptainer.*tito.sif\|singularity.*tito.sif" 2>/dev/null \
            | grep -qF "$SCRIPT_DIR"; then
            return 0
        fi
    fi
    return 1
}

run_hourly() {
    mkdir -p "$LOG_DIR"
    local ts
    ts=$(date -u +%Y%m%dT%H%M%S)
    local log="$LOG_DIR/tito_hourly_${ts}.log"

    exec 9>"$LOCK_FILE"
    if ! flock -n 9; then
        echo "==== TITO hourly SKIP $(date -u --iso-8601=seconds) ====" | tee -a "$log"
        echo "Previous run still holds $LOCK_FILE — not starting another cycle." | tee -a "$log"
        exit 0
    fi
    if tito_already_running; then
        echo "==== TITO hourly SKIP $(date -u --iso-8601=seconds) ====" | tee -a "$log"
        echo "A TITO $TITO_RUNTIME process for $SCRIPT_DIR is already running." | tee -a "$log"
        exit 0
    fi

    exec > >(stdbuf -oL -eL tee -a "$log") 2>&1

    echo "==== TITO hourly $TITO_RUNTIME run $(date -u --iso-8601=seconds) ===="
    echo "Region : $REGION"
    echo "Res    : (from region_resolution_map in Caribbean_Comoros_config.py)"
    echo "Runtime: $TITO_RUNTIME"
    echo "Log    : $log"

    if [ ! -x "$TITO_RUN" ]; then
        echo "ERROR: tito-run.sh missing or not executable: $TITO_RUN"
        exit 1
    fi
    chmod +x "$TITO_RUN" 2>/dev/null || true
    if [ "$TITO_RUNTIME" = "apptainer" ] || [ "$TITO_RUNTIME" = "singularity" ]; then
        if [ ! -f "$SCRIPT_DIR/tito.sif" ]; then
            echo "ERROR: tito.sif not found in $SCRIPT_DIR"
            echo "  Build/copy SIF, or set TITO_RUNTIME=docker"
            exit 1
        fi
        if ! command -v "$TITO_RUNTIME" >/dev/null 2>&1 && ! command -v apptainer >/dev/null 2>&1 && ! command -v singularity >/dev/null 2>&1; then
            echo "ERROR: apptainer/singularity not on PATH (cron PATH is $PATH)"
            exit 1
        fi
    fi

    cd "$SCRIPT_DIR" || return 1
    local rc=0
    TITO_RUNTIME="$TITO_RUNTIME" "$TITO_RUN" operational --regions "$REGION" \
        && echo "OK: $REGION operational" \
        || { echo "WARNING: TITO operational exited non-zero"; rc=1; }
    echo "==== TITO hourly run finished $(date -u --iso-8601=seconds) rc=$rc ===="
    return "$rc"
}

install_cron() {
    if crontab -l 2>/dev/null | grep -qF "$SCRIPT_DIR/manage_cron.sh run"; then
        echo "✓ Cron job already installed:"
        crontab -l | grep "$SCRIPT_DIR/manage_cron.sh"
        return 0
    fi
    chmod +x "$0" "$TITO_RUN" 2>/dev/null || true
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    if [ $? -eq 0 ]; then
        echo "✓ Cron job installed"
        echo "  Schedule : $CRON_SCHEDULE  (hh:05 UTC)"
        echo "  Command  : $CRON_CMD"
        echo "  Region   : $REGION"
        echo "  Runtime  : $TITO_RUNTIME"
    else
        echo "✗ Failed to install cron job"
        return 1
    fi
}

remove_cron() {
    if ! crontab -l 2>/dev/null | grep -qF "$SCRIPT_DIR/manage_cron.sh run"; then
        echo "✓ Cron job not found (already removed or never installed)"
        return 0
    fi
    crontab -l 2>/dev/null | grep -vF "$SCRIPT_DIR/manage_cron.sh run" | crontab -
    if [ $? -eq 0 ]; then
        echo "✓ Cron job removed"
    else
        echo "✗ Failed to remove cron job"
        return 1
    fi
}

show_status() {
    echo "=== TITO Cron Job Status ==="
    echo "  Region   : $REGION"
    echo "  Res      : (from region_resolution_map in Caribbean_Comoros_config.py)"
    echo "  Runtime  : $TITO_RUNTIME"
    echo ""
    if systemctl is-active --quiet cron 2>/dev/null || systemctl is-active --quiet crond 2>/dev/null; then
        echo "✓ Cron service is running"
    else
        echo "⚠ Cron service status unknown"
    fi
    echo ""
    if crontab -l 2>/dev/null | grep -qF "$SCRIPT_DIR/manage_cron.sh run"; then
        echo "✓ Cron job is INSTALLED"
        crontab -l | grep "$SCRIPT_DIR/manage_cron.sh"
        echo ""
        echo "Recent logs:"
        ls -lht "$LOG_DIR"/tito_hourly_*.log 2>/dev/null | head -5 \
            || echo "  No logs yet in $LOG_DIR"
        LAST_LOG=$(ls -t "$LOG_DIR"/tito_hourly_*.log 2>/dev/null | head -1)
        if [ -n "$LAST_LOG" ]; then
            echo ""
            echo "Last 10 lines of $LAST_LOG:"
            tail -10 "$LAST_LOG"
        fi
    else
        echo "✗ Cron job is NOT installed"
        echo "  Run: $0 install"
    fi
}

case "${1:-}" in
    run)     run_hourly ;;
    install) install_cron ;;
    remove)  remove_cron ;;
    status)  show_status ;;
    *)
        echo "TITO Guatemala — $TITO_RUNTIME cron (single orchestrator run, multi-res)"
        echo ""
        echo "Usage: $0 [install|remove|status|run]"
        echo ""
        echo "  Knobs at top of this file:"
        echo "    REGION=$REGION"
        echo "    TITO_RUNTIME=$TITO_RUNTIME"
        echo "    CRON_SCHEDULE=$CRON_SCHEDULE"
        echo ""
        echo "  Resolutions come from region_resolution_map in Caribbean_Comoros_config.py"
        echo "  e.g. {\"Guatemala\": [\"900m\", \"90m\"]}"
        echo ""
        echo "  install   Hourly cron at hh:05 UTC → $TITO_RUNTIME operational (one run)"
        echo "  remove    Remove that cron entry"
        echo "  status    Show cron + recent log tail"
        echo "  run       Run now (same as cron); skips if a previous cycle is still running"
        echo ""
        echo "Example:"
        echo "  chmod +x $0 $TITO_RUN"
        echo "  $0 run"
        echo "  $0 install"
        exit 1
        ;;
esac
