"""Runtime configuration for the HK criminal law MCP server."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "hk-criminal-law-mcp"
VERSION = "0.4.0"

# Public endpoints. These are free-to-access sources, subject to their own terms.
HKLII_BASE = os.environ.get("HK_LAW_HKLII_BASE", "https://www.hklii.hk").rstrip("/")
ELEGISLATION_BASE = os.environ.get(
    "HK_LAW_ELEGISLATION_BASE", "https://www.elegislation.gov.hk"
).rstrip("/")
DATA_GOV_BASE = os.environ.get(
    "HK_LAW_DATA_GOV_BASE", "https://resource.data.one.gov.hk/doj/data"
).rstrip("/")
DOJ_BASE = os.environ.get("HK_LAW_DOJ_BASE", "https://www.doj.gov.hk").rstrip("/")

# DOJ pages are static and small; a shorter interval than HKLII is still polite.
DOJ_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("HK_LAW_DOJ_REQUEST_INTERVAL", "0.5")
)

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


def semantic_map_dir() -> Path:
    """Return the generated semantic-atlas data directory.

    ``HK_LAW_SEMANTIC_MAP`` wins. Otherwise use the repository copy when the
    package is running from a checkout. The global installer sets the env var
    explicitly for installed copies.
    """
    raw = os.environ.get("HK_LAW_SEMANTIC_MAP")
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[2] / "semantic_map" / "dist" / "data"


def local_only() -> bool:
    """Return True when all live network retrieval must be disabled.

    The MCP launcher sets this by default so the server is fully local. Set
    ``HK_LAW_LOCAL_ONLY=0`` only when a permitted live source is configured.
    """
    return os.environ.get("HK_LAW_LOCAL_ONLY", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def live_case_default() -> bool:
    """Return True when case reads should use the permitted live source.

    This is the inverse of :func:`local_only`. The public launcher sets
    ``HK_LAW_LOCAL_ONLY=1``, so live access is off by default. An operator who
    needs query-time coverage of the whole HKLII database can set
    ``HK_LAW_LOCAL_ONLY=0``; the MCP tool defaults then use live retrieval,
    subject to HKLII's terms. Bulk sync still requires a permission reference.
    """
    return not local_only()


def case_permission_ref() -> str | None:
    """Return the written-permission reference for automated case access.

    This is deliberately not a URL. It records *why* the operator is allowed to
    use the configured source (for example, a Judiciary/HKLII permission letter
    reference). The sync code refuses to run without it.
    """
    value = os.environ.get("HK_LAW_CASE_PERMISSION_REF", "").strip()
    return value or None


def case_source_url() -> str | None:
    """Return the permitted case-source endpoint, if one is configured."""
    value = os.environ.get("HK_LAW_CASE_SOURCE_URL", "").strip()
    return value or None


def case_source_name() -> str:
    """Return the operator-facing name of the configured case source."""
    return os.environ.get("HK_LAW_CASE_SOURCE", "authorized-import").strip() or "authorized-import"


def case_import_dir() -> Path | None:
    """Return the optional drop folder scanned by ``hk-law sync``."""
    raw = os.environ.get("HK_LAW_CASE_IMPORT_DIR", "").strip()
    return Path(raw).expanduser() if raw else None


def case_citations_file() -> Path | None:
    """Return the optional, permission-gated citation list for ``sync``."""
    raw = os.environ.get("HK_LAW_CASE_CITATIONS", "").strip()
    return Path(raw).expanduser() if raw else None
