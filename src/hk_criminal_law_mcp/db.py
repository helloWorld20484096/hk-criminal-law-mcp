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
"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open the database with the project defaults and initialise the schema."""
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def stats(conn: sqlite3.Connection) -> dict:
    """Return corpus counts and the freshest ingest metadata."""
    def one(sql: str, *args):
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else 0

    docs = one("SELECT COUNT(*) FROM legislation_docs")
    sections = one("SELECT COUNT(*) FROM legislation_sections")
    cases = one("SELECT COUNT(*) FROM cases")
    paragraphs = one("SELECT COUNT(*) FROM case_paragraphs")
    en = one("SELECT COUNT(*) FROM legislation_sections WHERE language='en'")
    zh = one("SELECT COUNT(*) FROM legislation_sections WHERE language LIKE 'zh%'")
    return {
        "legislation_docs": docs,
        "legislation_sections": sections,
        "legislation_sections_en": en,
        "legislation_sections_zh": zh,
        "cases": cases,
        "case_paragraphs": paragraphs,
        "database": str(conn.execute("PRAGMA database_list").fetchone()[2]),
        "last_legislation_ingest": one(
            "SELECT MAX(ingested_at) FROM legislation_docs"
        ),
        "last_case_fetch": one("SELECT MAX(fetched_at) FROM cases"),
    }
