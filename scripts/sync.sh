#!/usr/bin/env bash
# One-shot local corpus sync. Safe to run from cron or a systemd user timer.
#
#   ./scripts/sync.sh                 # legislation + DOJ, plus any env-configured cases
#   ./scripts/sync.sh --no-doj        # skip the DOJ publications
#   ./scripts/sync.sh --dataset both  # also refresh historical legislation
#
# Case access is permission-gated. Set these only after reading
# docs/full-local-pipeline.md and obtaining written permission:
#   HK_LAW_CASE_PERMISSION_REF   written-permission reference (required)
#   HK_LAW_CASE_CITATIONS        explicit citation list for the HKLII adapter
#   HK_LAW_CASE_IMPORT_DIR       authorised judgment drop folder
#   HK_LAW_CASE_SOURCE           hklii (only wired adapter) or authorized-import
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export HK_LAW_DB="${HK_LAW_DB:-$ROOT/data/hk_law.db}"
export HK_LAW_DATA_DIR="${HK_LAW_DATA_DIR:-$ROOT/data/raw}"
export HK_LAW_SEMANTIC_MAP="${HK_LAW_SEMANTIC_MAP:-$ROOT/semantic_map/dist/data}"

if [[ -x "$ROOT/.venv/bin/hk-law" ]]; then
  HK_LAW="$ROOT/.venv/bin/hk-law"
elif command -v hk-law >/dev/null 2>&1; then
  HK_LAW="$(command -v hk-law)"
else
  echo "hk-law not found. Install the package first: .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

echo "[$(date -Is)] hk-law sync starting (db=$HK_LAW_DB)"
exec "$HK_LAW" --db "$HK_LAW_DB" sync \
  --data-dir "$HK_LAW_DATA_DIR" \
  --dataset "${HK_LAW_SYNC_DATASET:-current}" \
  "$@"
