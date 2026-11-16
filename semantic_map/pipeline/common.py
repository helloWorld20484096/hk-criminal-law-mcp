"""Shared paths and helpers for the semantic-map pipeline."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "hk_law.db"
SEMANTIC = ROOT / "semantic_map"
DATA = SEMANTIC / "data"
WORK = DATA / "work"
DIST = SEMANTIC / "dist"
WEB = SEMANTIC / "web"

for _path in (DATA, WORK, DIST, WEB, WEB / "vendor"):
    _path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
