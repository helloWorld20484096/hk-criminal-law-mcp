"""Runtime configuration for the HK criminal law MCP server."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "hk-criminal-law-mcp"
VERSION = "0.2.0"

# Public endpoints. These are free-to-access sources, subject to their own terms.
HKLII_BASE = os.environ.get("HK_LAW_HKLII_BASE", "https://www.hklii.hk").rstrip("/")
ELEGISLATION_BASE = os.environ.get(
    "HK_LAW_ELEGISLATION_BASE", "https://www.elegislation.gov.hk"
).rstrip("/")
DATA_GOV_BASE = os.environ.get(
    "HK_LAW_DATA_GOV_BASE", "https://resource.data.one.gov.hk/doj/data"
).rstrip("/")

# Be polite to public services. HKLII is a small public-interest service.
REQUEST_INTERVAL_SECONDS = float(os.environ.get("HK_LAW_REQUEST_INTERVAL", "1.5"))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("HK_LAW_REQUEST_TIMEOUT", "60"))
USER_AGENT = os.environ.get(
    "HK_LAW_USER_AGENT",
    f"{APP_NAME}/{VERSION} (+local research tool; respects source terms)",
)

DISCLAIMER = (
    "Research assistance only, not legal advice. Verify every provision and "
    "judgment against the official source before relying on it. Hong Kong "
    "criminal law changes; check commencement, amendments and subsequent "
    "judicial treatment."
)


def home_dir() -> Path:
    """Return the writable application home directory."""
    raw = os.environ.get("HK_LAW_HOME")
    base = Path(raw).expanduser() if raw else Path.home() / ".local" / "share" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    """Return the SQLite database path, creating its parent directory."""
    raw = os.environ.get("HK_LAW_DB")
    path = Path(raw).expanduser() if raw else home_dir() / "hk_law.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Return the directory used for downloaded archives."""
    raw = os.environ.get("HK_LAW_DATA_DIR")
    path = Path(raw).expanduser() if raw else home_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path
