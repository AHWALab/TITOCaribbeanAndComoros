#!/bin/bash
#$ -S /bin/bash
#$ -pe smp 56
#$ -cwd
#$ -j y
#$ -N tito_ab_hourly
#$ -o tito_ab_hourly.log
#$ -M naman-mehta@uiowa.edu
#$ -m be
# ============================================================================
# tito_ab_hourly_job.sh — hourly TITO operational cycles on Argon (SGE)
# ============================================================================
# Cron is not available on the HPC, so this single long-running SGE job acts as
# the cron replacement: it holds the allocation and fires one TITO operational
# cycle every hour at hh:05 UTC, exactly like `manage_cron.sh install` did.
#
#   Submit :  qsub tito_ab_hourly_job.sh
#   Watch  :  qstat -j <job_id>      |  tail -f tito_ab_hourly.log
#   Stop   :  qdel <job_id>
#
# Runtime   : apptainer  (project-local tito.sif + EF5/bin/ef5, no Docker)
# Resources : 56 slots. ef5_max_workers = None in Caribbean_Comoros_config.py
#             so every EF5 ensemble job fans out concurrently (each EF5 run is
#             single-threaded, OMP_NUM_THREADS=1) — full parallelization.
# Region    : Antigua @ 30m (from region_resolution_map in the config)
# ============================================================================

set -u
SCRIPT_DIR="/Dedicated/Humberto/WMO_Caribbean_Comoros/TITO/Deployment_versions/AB"

# ── Runtime selection: Apptainer, never Docker on the HPC ──────────────────
export TITO_RUNTIME="apptainer"
export TITO_SIF="$SCRIPT_DIR/tito.sif"
export EF5_LOCAL_BIN="$SCRIPT_DIR/EF5/bin/ef5"
export TZ="Etc/UTC"

# EF5 jobs are single-threaded and fanned out one process per CPU; keep OpenMP
# from oversubscribing the slots.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export EF5_OMP_NUM_THREADS="${EF5_OMP_NUM_THREADS:-1}"

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
module load apptainer 2>/dev/null || module load singularity 2>/dev/null || true

cd "$SCRIPT_DIR" || { echo "ERROR: cannot cd to $SCRIPT_DIR"; exit 1; }

LOG_DIR="$SCRIPT_DIR/outputs/logs"
mkdir -p "$LOG_DIR"

echo "==================================================================="
echo "TITO AB hourly SGE job $JOB_ID on $(hostname)"
echo "  Start   : $(date -u --iso-8601=seconds)"
echo "  Slots   : ${NSLOTS:-?}  (pe smp 56)"
echo "  Runtime : $TITO_RUNTIME"
echo "  SIF     : $TITO_SIF"
echo "  EF5 bin : $EF5_LOCAL_BIN"
echo "  Schedule: hh:05 UTC, every hour"
echo "==================================================================="

if command -v apptainer >/dev/null 2>&1; then
    echo "apptainer: $(apptainer --version 2>/dev/null)"
else
    echo "ERROR: apptainer not on PATH. Try: module load apptainer" >&2
    exit 1
fi
if [[ ! -f "$TITO_SIF" ]]; then
    echo "ERROR: TITO SIF not found: $TITO_SIF" >&2
    exit 1
fi
if [[ ! -x "$EF5_LOCAL_BIN" ]]; then
    echo "ERROR: EF5 binary not executable: $EF5_LOCAL_BIN" >&2
    exit 1
fi

# Seconds until the next hh:05:00 UTC
seconds_until_hh05() {
    local now_s now_m into target
    now_s=$(date -u +%S)
    now_m=$(date -u +%M)
    into=$((10#$now_m * 60 + 10#$now_s))
    target=$((5 * 60))
    if [ "$into" -lt "$target" ]; then
        echo $((target - into))
    else
        echo $((3600 - into + target))
    fi
}

run_cycle() {
    echo ""
    echo "==== TITO cycle $(date -u --iso-8601=seconds) ===="
    # manage_cron.sh keeps the flock/tito-already-running guard, so a cycle that
    # overruns into the next hour simply skips instead of overlapping.
    "$SCRIPT_DIR/manage_cron.sh" run
    echo "==== TITO cycle done $(date -u --iso-8601=seconds) rc=$? ===="
}

trap 'echo "[$(date -u --iso-8601=seconds)] received stop signal — exiting hourly loop"; exit 0' TERM INT

# First cycle immediately, then align to hh:05 UTC every hour.
run_cycle

while true; do
    wait_s=$(seconds_until_hh05)
    echo "[$(date -u --iso-8601=seconds)] sleeping ${wait_s}s until next hh:05 UTC"
    sleep "$wait_s"
    run_cycle
done
