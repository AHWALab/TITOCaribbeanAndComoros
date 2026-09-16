#!/bin/bash
# Publish outputs/ to S3 as a rolling 24h mirror.
#
# The local pipeline already prunes outputs/ to `outputs_keep_hours = 24`
# (tito_utils/postprocess/archive_manager.py, run at the end of every cycle in
# orchestrator.py). This script mirrors that exact state with `sync --delete`,
# so S3 tracks the same 24h window. Deletion is driven from the local side;
# we do NOT rely on lifecycle rules for the 24h window because S3 lifecycle
# expiration only works in whole days. The optional lifecycle rule below is a
# backstop for stale objects if publishing ever stops.
#
# Usage:
#   TITO_S3_BUCKET=my-bucket ./publish_outputs_to_s3.sh
#   TITO_S3_BUCKET=my-bucket ./publish_outputs_to_s3.sh --create-bucket
#   TITO_S3_BUCKET=my-bucket ./publish_outputs_to_s3.sh --dryrun
#
# Env knobs:
#   TITO_S3_BUCKET          required bucket name (unset => no-op, exit 0)
#   TITO_S3_PREFIX          optional key prefix, e.g. caribbean-comoros
#   AWS_REGION / AWS_DEFAULT_REGION   bucket region (default us-east-2)
#   TITO_S3_LIFECYCLE_DAYS  optional backstop expiry in whole days; 0 disables
#   TITO_S3_SYNC_EXTRA      extra raw args appended to `aws s3 sync`

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BUCKET="${TITO_S3_BUCKET:-}"
PREFIX="${TITO_S3_PREFIX:-}"
REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
LIFECYCLE_DAYS="${TITO_S3_LIFECYCLE_DAYS:-0}"
OUTPUTS_DIR="$SCRIPT_DIR/outputs"

DRY_RUN=0
CREATE_BUCKET=0
for arg in "$@"; do
  case "$arg" in
    --dryrun|--dry-run) DRY_RUN=1 ;;
    --create-bucket)    CREATE_BUCKET=1 ;;
    -h|--help)          sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ -z "$BUCKET" ]; then
  echo "TITO_S3_BUCKET is not set — skipping S3 publish."
  exit 0
fi

if [ ! -d "$OUTPUTS_DIR" ]; then
  echo "ERROR: outputs directory not found: $OUTPUTS_DIR" >&2
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "ERROR: aws CLI not on PATH" >&2
  exit 1
fi

# ── Bucket ────────────────────────────────────────────────────────────────
bucket_exists() {
  aws s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1
}

if ! bucket_exists; then
  if [ "$CREATE_BUCKET" != "1" ]; then
    echo "ERROR: cannot access bucket '$BUCKET'." >&2
    echo "  (bucket may not exist, or AWS credentials/permissions are missing)" >&2
    aws s3api head-bucket --bucket "$BUCKET" >/dev/null || true
    exit 1
  fi
  if [ "$DRY_RUN" = "1" ]; then
    echo "WOULD CREATE: s3://$BUCKET (region $REGION)"
  else
    echo "Creating s3://$BUCKET in $REGION …"
    if [ "$REGION" = "us-east-1" ]; then
      aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
    else
      aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
        --create-bucket-configuration LocationConstraint="$REGION"
    fi
    aws s3api put-public-access-block --bucket "$BUCKET" \
      --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
    aws s3api put-bucket-encryption --bucket "$BUCKET" \
      --server-side-encryption-configuration \
      '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  fi
fi

# ── Optional lifecycle backstop ───────────────────────────────────────────
if [ "$LIFECYCLE_DAYS" -ge 1 ] 2>/dev/null; then
  if [ -n "$PREFIX" ]; then
    FILTER="{\"Prefix\":\"$PREFIX\"}"
  else
    FILTER="{}"
  fi
  LIFECYCLE_JSON="{\"Rules\":[{\"ID\":\"tito-outputs-backstop\",\"Status\":\"Enabled\",\"Filter\":$FILTER,\"Expiration\":{\"Days\":$LIFECYCLE_DAYS}}]}"
  if [ "$DRY_RUN" = "1" ]; then
    echo "WOULD SET lifecycle: expire objects after ${LIFECYCLE_DAYS}d on s3://$BUCKET"
  else
    aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" \
      --lifecycle-configuration "$LIFECYCLE_JSON"
    echo "Lifecycle backstop: expire after ${LIFECYCLE_DAYS}d"
  fi
fi

# ── Mirror outputs/ (24h cycle folders only) ──────────────────────────────
SYNC_DST="s3://$BUCKET"
[ -n "$PREFIX" ] && SYNC_DST="s3://$BUCKET/$PREFIX"

SYNC_ARGS=(
  s3 sync "$OUTPUTS_DIR/" "$SYNC_DST"
  --delete
  --exclude "logs/*"
  --exclude ".gitkeep"
  --only-show-errors
)
[ "$DRY_RUN" = "1" ] && SYNC_ARGS+=(--dryrun)
# shellcheck disable=SC2206
[ -n "${TITO_S3_SYNC_EXTRA:-}" ] && SYNC_ARGS+=($TITO_S3_SYNC_EXTRA)

echo "Mirroring $OUTPUTS_DIR/ -> $SYNC_DST (delete, logs excluded)"
aws "${SYNC_ARGS[@]}"
echo "S3 publish complete."
