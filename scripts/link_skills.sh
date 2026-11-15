#!/usr/bin/env bash
# Link the repository's skills into .claude/skills for project-scoped discovery.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/.claude/skills"

for skill in "$ROOT"/skills/*/; do
  [[ -f "$skill/SKILL.md" ]] || continue
  name="$(basename "$skill")"
  ln -sfn "../../skills/$name/" "$ROOT/.claude/skills/$name"
done

echo "linked $(find "$ROOT/.claude/skills" -maxdepth 1 -type l | wc -l) skills into .claude/skills"
