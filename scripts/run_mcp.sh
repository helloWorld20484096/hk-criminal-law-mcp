#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "hk-criminal-law-mcp: missing $VENV_PY" >&2
  echo "Run: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

export HK_LAW_DB="${HK_LAW_DB:-$ROOT/data/hk_law.db}"
export HK_LAW_DATA_DIR="${HK_LAW_DATA_DIR:-$ROOT/data/raw}"
# Fully local by default. Set HK_LAW_LOCAL_ONLY=0 only after a permitted live
# source is configured (see docs/full-local-pipeline.md).
export HK_LAW_LOCAL_ONLY="${HK_LAW_LOCAL_ONLY:-1}"

exec "$VENV_PY" -m hk_criminal_law_mcp.server
