#!/usr/bin/env bash
# Run the remote server with the project virtualenv.
# Examples:
#   scripts/serve_http.sh                      # localhost, anonymous
#   scripts/serve_http.sh --access-key "$KEY"  # localhost, key required
#   scripts/serve_http.sh --access-key "$KEY" --public-url https://hk-law.example.com
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export HK_LAW_DB="${HK_LAW_DB:-$ROOT/data/hk_law.db}"
export HK_LAW_DATA_DIR="${HK_LAW_DATA_DIR:-$ROOT/data/raw}"

if [[ -x "$ROOT/.venv/bin/hk-law" ]]; then
  exec "$ROOT/.venv/bin/hk-law" serve-http "$@"
fi

exec hk-law serve-http "$@"
