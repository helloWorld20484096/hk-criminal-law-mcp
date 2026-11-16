"""SQLite schema and connection helpers.

The database is intentionally a single portable SQLite file. Legislation is
indexed locally as a citable corpus; judgments fetched from HKLII are cached
locally and are never redistributed with this project.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import db_path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legislation_docs (
    id INTEGER PRIMARY KEY,
    cap TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'cap',
    doc_number TEXT NOT NULL,
    doc_name TEXT,
    title TEXT,
    long_title TEXT,
    language TEXT NOT NULL,
    version_date TEXT,
    status TEXT,
    source_url TEXT,
    source_file TEXT,
    checksum TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (cap, doc_type, language)
);

CREATE TABLE IF NOT EXISTS legislation_sections (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES legislation_docs(id) ON DELETE CASCADE,
    cap TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'cap',
    section_key TEXT NOT NULL,
    section_no TEXT,
    heading TEXT,
    text TEXT NOT NULL,
    part TEXT,
    division TEXT,
    language TEXT NOT NULL,
    version_date TEXT,
    source_url TEXT,
    source_note TEXT,
    UNIQUE (doc_id, section_key)
);

CREATE INDEX IF NOT EXISTS idx_leg_sections_cap ON legislation_sections(cap, language);
CREATE INDEX IF NOT EXISTS idx_leg_sections_no ON legislation_sections(cap, section_no, language);

-- Historical versions from the DATA.GOV.HK "Past Version" archives. Kept
-- separate from the current corpus so current-version lookups stay fast and
-- unambiguous.
CREATE TABLE IF NOT EXISTS legislation_history_docs (
    id INTEGER PRIMARY KEY,
    cap TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'cap',
    doc_number TEXT NOT NULL,
    doc_name TEXT,
    title TEXT,
    long_title TEXT,
    language TEXT NOT NULL,
    version_date TEXT NOT NULL,
    status TEXT,
    source_url TEXT,
    source_file TEXT,
    checksum TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (cap, doc_type, language, version_date)
);

CREATE TABLE IF NOT EXISTS legislation_history_sections (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL REFERENCES legislation_history_docs(id) ON DELETE CASCADE,
    cap TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'cap',
    section_key TEXT NOT NULL,
    section_no TEXT,
    heading TEXT,
    text TEXT NOT NULL,
    part TEXT,
    division TEXT,
    language TEXT NOT NULL,
    version_date TEXT NOT NULL,
    source_url TEXT,
    source_note TEXT,
    UNIQUE (doc_id, section_key)
);

CREATE INDEX IF NOT EXISTS idx_hist_docs_cap
    ON legislation_history_docs(cap, language, version_date);
CREATE INDEX IF NOT EXISTS idx_hist_sections_lookup
    ON legislation_history_sections(cap, section_no, language, version_date);
CREATE INDEX IF NOT EXISTS idx_hist_sections_key
    ON legislation_history_sections(cap, section_key, language, version_date);

CREATE VIRTUAL TABLE IF NOT EXISTS legislation_fts_en USING fts5(
    section_id UNINDEXED,
    cap UNINDEXED,
    section_no UNINDEXED,
    heading,
    text,
    tokenize = 'porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS legislation_fts_zh USING fts5(
    section_id UNINDEXED,
    cap UNINDEXED,
    section_no UNINDEXED,
    heading,
    text,
    tokenize = 'trigram'
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY,
    neutral_citation TEXT NOT NULL,
    court TEXT,
    court_code TEXT,
    year INTEGER,
    num TEXT,
    title TEXT,
    judgment_date TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    source_url TEXT,
    doc_url TEXT,
    html TEXT,
    text TEXT,
    paragraphs_json TEXT,
    cited_cases_json TEXT,
    parallel_citation TEXT,
    is_translation INTEGER,
    has_translation INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    checksum TEXT,
    UNIQUE (neutral_citation, language)
);

CREATE TABLE IF NOT EXISTS case_paragraphs (
    case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    para_no TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (case_id, para_no)
);

CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts_en USING fts5(
    case_id UNINDEXED,
    neutral_citation UNINDEXED,
    title,
    text,
    tokenize = 'porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts_zh USING fts5(
    case_id UNINDEXED,
    neutral_citation UNINDEXED,
    title,
    text,
    tokenize = 'trigram'
);

CREATE TABLE IF NOT EXISTS case_noteups (
    case_id INTEGER PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS case_search_cache (
    query_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Audit trail for every sync/import run. A run that crashes stays 'running'
-- with a non-null error, so the next sync can report the failed attempt.
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    source TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    stats_json TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_started ON sync_runs(started_at);

-- Provenance for locally imported judgment corpora. A source row is written
-- only after an import or an explicitly permission-gated sync.
CREATE TABLE IF NOT EXISTS case_sources (
    source TEXT PRIMARY KEY,
    license TEXT,
    permission_ref TEXT,
    base_url TEXT,
    imported_at TEXT,
    last_sync_at TEXT,
    case_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cases_court_year ON cases(court_code, year);
CREATE INDEX IF NOT EXISTS idx_cases_judgment_date ON cases(judgment_date);
"""


def _normalise_version_dates(conn: sqlite3.Connection) -> None:
    """Trim ISO timestamps in version dates to YYYY-MM-DD (legacy rows)."""
    conn.execute(
        "UPDATE OR IGNORE legislation_docs "
        "SET version_date=substr(version_date,1,10) "
        "WHERE length(version_date)>10"
    )
    conn.execute(
        "UPDATE OR IGNORE legislation_history_docs "
        "SET version_date=substr(version_date,1,10) "
        "WHERE length(version_date)>10"
    )
    conn.execute(
        "UPDATE legislation_history_sections "
        "SET version_date=substr(version_date,1,10) "
        "WHERE length(version_date)>10"
    )
    conn.commit()


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the database with the project defaults and initialise the schema."""
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    try:
        _normalise_version_dates(conn)
    except sqlite3.OperationalError:
        # A concurrent ingest may hold the write lock; the next connection retries.
        pass
    return conn


def stats(conn: sqlite3.Connection) -> dict:
    """Return corpus counts and the freshest ingest metadata."""
    def one(sql: str, *args):
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else 0

    docs = one("SELECT COUNT(*) FROM legislation_docs")
    sections = one("SELECT COUNT(*) FROM legislation_sections")
    history_docs = one("SELECT COUNT(*) FROM legislation_history_docs")
    history_sections = one("SELECT COUNT(*) FROM legislation_history_sections")
    cases = one("SELECT COUNT(*) FROM cases")
    paragraphs = one("SELECT COUNT(*) FROM case_paragraphs")
    case_sources = one("SELECT COUNT(*) FROM case_sources")
    sync_runs = one("SELECT COUNT(*) FROM sync_runs")
    en = one("SELECT COUNT(*) FROM legislation_sections WHERE language='en'")
    zh = one("SELECT COUNT(*) FROM legislation_sections WHERE language LIKE 'zh%'")
    hist_min = one("SELECT MIN(version_date) FROM legislation_history_docs")
    hist_max = one("SELECT MAX(version_date) FROM legislation_history_docs")
    cases_by_court = {
        row["court_code"]: row["n"]
        for row in conn.execute(
            "SELECT court_code, COUNT(*) AS n FROM cases "
            "WHERE court_code IS NOT NULL GROUP BY court_code ORDER BY n DESC"
        ).fetchall()
    }
    return {
        "legislation_docs": docs,
        "legislation_sections": sections,
        "legislation_sections_en": en,
        "legislation_sections_zh": zh,
        "legislation_history_docs": history_docs,
        "legislation_history_sections": history_sections,
        "legislation_history_date_range": (
            f"{hist_min} .. {hist_max}" if history_docs else None
        ),
        "cases": cases,
        "case_paragraphs": paragraphs,
        "case_sources": case_sources,
        "cases_by_court": cases_by_court,
        "sync_runs": sync_runs,
        "last_case_import": one("SELECT MAX(imported_at) FROM case_sources"),
        "last_sync": one(
            "SELECT MAX(finished_at) FROM sync_runs "
            "WHERE status IN ('ok','partial')"
        ),
        "database": str(conn.execute("PRAGMA database_list").fetchone()[2]),
        "last_legislation_ingest": one(
            "SELECT MAX(ingested_at) FROM legislation_docs"
        ),
        "last_history_ingest": one(
            "SELECT MAX(ingested_at) FROM legislation_history_docs"
        ),
        "last_case_fetch": one("SELECT MAX(fetched_at) FROM cases"),
    }
