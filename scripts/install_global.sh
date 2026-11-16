#!/usr/bin/env bash
# Install the MCP server and skills for all projects (user scope).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GLOBAL_HOME="${HK_LAW_GLOBAL_HOME:-$HOME/.local/share/hk-criminal-law-mcp}"
SKILLS_HOME="$HOME/.claude/skills/hk-criminal-law"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v claude >/dev/null || { echo "Claude Code CLI is required" >&2; exit 1; }

mkdir -p "$GLOBAL_HOME"
if [[ ! -x "$GLOBAL_HOME/venv/bin/python" ]]; then
  python3 -m venv "$GLOBAL_HOME/venv"
fi
"$GLOBAL_HOME/venv/bin/pip" install -q --upgrade pip
"$GLOBAL_HOME/venv/bin/pip" install -q "$ROOT"

# Use the local corpus if it exists. Otherwise the user must build one first.
if [[ -f "$ROOT/data/hk_law.db" ]]; then
  if [[ -e "$GLOBAL_HOME/hk_law.db" && ! -L "$GLOBAL_HOME/hk_law.db" ]]; then
    echo "Keeping existing database: $GLOBAL_HOME/hk_law.db"
  else
    ln -sfn "$ROOT/data/hk_law.db" "$GLOBAL_HOME/hk_law.db"
  fi
else
  echo "No corpus at $ROOT/data/hk_law.db." >&2
  echo "Build one first:" >&2
  echo "  $ROOT/.venv/bin/hk-law download --data-dir $ROOT/data/raw" >&2
  echo "  $ROOT/.venv/bin/hk-law ingest --data-dir $ROOT/data/raw --language en" >&2
  echo "  $ROOT/.venv/bin/hk-law ingest --data-dir $ROOT/data/raw --language zh-Hant" >&2
fi

# Global skills plugin (one skills-dir plugin with all 12 skills).
mkdir -p "$SKILLS_HOME/.claude-plugin" "$SKILLS_HOME/skills"
cp "$ROOT/.claude-plugin/plugin.json" "$SKILLS_HOME/.claude-plugin/plugin.json"
for dir in "$ROOT"/skills/*/; do
  [[ -f "$dir/SKILL.md" ]] || continue
  name="$(basename "$dir")"
  rm -rf "$SKILLS_HOME/skills/$name"
  cp -R "$dir" "$SKILLS_HOME/skills/$name"
done

# User-scope MCP server (available in every project).
if claude mcp get hk-criminal-law >/dev/null 2>&1; then
  claude mcp remove hk-criminal-law -s user >/dev/null 2>&1 || true
fi
claude mcp add --scope user hk-criminal-law \
  -e "HK_LAW_DB=$GLOBAL_HOME/hk_law.db" \
  -e "HK_LAW_LOCAL_ONLY=0" \
  -- "$GLOBAL_HOME/venv/bin/python" -m hk_criminal_law_mcp.server

echo
echo "Installed."
echo "  MCP:    claude mcp get hk-criminal-law"
echo "  Skills: $SKILLS_HOME"
echo "  Data:   $GLOBAL_HOME/hk_law.db"
