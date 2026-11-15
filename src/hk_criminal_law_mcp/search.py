"""Search and citation-verification helpers over the local corpus."""

from __future__ import annotations

import re
import sqlite3

from .citations import (
    LegislationCitation,
    normalise_cap,
    normalise_section,
    parse_case_citation,
    parse_legislation_citation,
)
from .hklii import HKLIIError, get_judgment

_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def _fts_table(lang: str) -> str:
    return "legislation_fts_en" if lang == "en" else "legislation_fts_zh"


def _match_query(query: str, lang: str) -> str | None:
    query = query.strip()
    if not query:
        return None
    if lang == "en":
        words = _WORD_RE.findall(query)
        if not words:
            return None
        return " AND ".join(f'"{w}"' for w in words)
    # trigram tokenizer: a quoted phrase gives substring matching for Chinese.
    if len(query) < 3:
        return None
    return '"' + query.replace('"', '""') + '"'


def _section_citation(cap: str, section_no: str) -> str:
    if str(section_no).lower().startswith("sch"):
        return f"Cap. {cap} {section_no.replace('sch', 'Sch. ')}"
    return f"Cap. {cap} s.{section_no}"


def _row_to_legislation(
    row: sqlite3.Row, include_text: bool = False, max_chars: int = 20000
) -> dict:
    item = {
        "citation": _section_citation(row["cap"], row["section_no"] or row["section_key"]),
        "cap": row["cap"],
        "section": row["section_no"],
        "heading": row["heading"],
        "part": row["part"],
        "division": row["division"],
        "language": row["language"],
        "version_date": row["version_date"],
        "source_url": row["source_url"],
        "document_title": row["title"] if "title" in row.keys() else None,
        "snippet": row["snip"] if "snip" in row.keys() else None,
        "verified": "local_corpus",
    }
    if include_text:
        text = row["text"] or ""
        if len(text) > max_chars:
            item["text"] = text[:max_chars]
            item["truncated"] = True
            item["full_length"] = len(text)
        else:
            item["text"] = text
        item["source_note"] = row["source_note"]
    return item


def search_legislation(
    conn: sqlite3.Connection,
    query: str,
    cap: str | None = None,
    lang: str = "en",
    limit: int = 8,
    include_text: bool = False,
    max_chars: int = 4000,
) -> dict:
    """Full-text search over the locally indexed HKeL corpus."""
    lang = "en" if lang == "en" else "zh-Hant"
    table = _fts_table(lang)
    match = _match_query(query, lang)
    cap_norm = normalise_cap(cap) if cap else None
    limit = max(1, min(limit, 50))
    rows: list[sqlite3.Row] = []

    if match:
        sql = f"""
            SELECT s.*, d.title, snippet({table}, 4, '[', ']', ' … ', 28) AS snip,
                   bm25({table}) AS rank
            FROM {table}
            JOIN legislation_sections s ON s.id = {table}.section_id
            JOIN legislation_docs d ON d.id = s.doc_id
            WHERE {table} MATCH ?
        """
        params: list = [match]
        if cap_norm:
            sql += " AND s.cap = ?"
            params.append(cap_norm)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            rows = []

    if not rows:
        # Fallbacks: OR terms, then LIKE. Keep results clearly marked.
        if lang == "en" and match:
            words = _WORD_RE.findall(query)
            if len(words) > 1:
                try:
                    rows = conn.execute(
                        f"""
                        SELECT s.*, d.title, snippet({table}, 4, '[', ']', ' … ', 28) AS snip,
                               bm25({table}) AS rank
                        FROM {table}
                        JOIN legislation_sections s ON s.id = {table}.section_id
                        JOIN legislation_docs d ON d.id = s.doc_id
                        WHERE {table} MATCH ?
                        {"AND s.cap = ?" if cap_norm else ""}
                        ORDER BY rank LIMIT ?
                        """,
                        (
                            [" OR ".join(f'"{w}"' for w in words), cap_norm, limit]
                            if cap_norm
                            else [" OR ".join(f'"{w}"' for w in words), limit]
                        ),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
        if not rows:
            like = f"%{query}%"
            sql = """
                SELECT s.*, d.title, substr(s.text, 1, 240) AS snip
                FROM legislation_sections s
                JOIN legislation_docs d ON d.id = s.doc_id
                WHERE s.language = ? AND (s.text LIKE ? OR s.heading LIKE ?)
            """
            params = [lang, like, like]
            if cap_norm:
                sql += " AND s.cap = ?"
                params.append(cap_norm)
            sql += " LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()

    results = [
        _row_to_legislation(row, include_text=include_text, max_chars=max_chars)
        for row in rows
    ]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "corpus": "Hong Kong e-Legislation current version (data.gov.hk XML)",
        "warning": (
            "Search results are retrieval aids. Read the full provision and check "
            "commencement/amendments before relying on it."
        ),
    }


def get_section(
    conn: sqlite3.Connection,
    cap: str,
    section: str,
    lang: str = "en",
    max_chars: int = 20000,
) -> dict:
    """Return one section or schedule by Cap number and section number."""
    lang = "en" if lang == "en" else "zh-Hant"
    cap_norm = normalise_cap(cap)
    section_norm = normalise_section(section)
    candidates = {section_norm, f"s{section_norm}", f"sch{section_norm}"}
    placeholders = ",".join("?" for _ in candidates)
    row = conn.execute(
        f"""
        SELECT s.*, d.title, d.long_title, d.doc_name, d.version_date AS doc_version,
               d.source_url AS doc_source_url
        FROM legislation_sections s
        JOIN legislation_docs d ON d.id = s.doc_id
        WHERE s.cap = ? AND s.language = ?
          AND (s.section_no IN ({placeholders}) COLLATE NOCASE
               OR s.section_key IN ({placeholders}) COLLATE NOCASE)
        ORDER BY s.id
        LIMIT 1
        """,
        [cap_norm, lang, *candidates, *candidates],
    ).fetchone()
    if not row:
        doc = conn.execute(
            "SELECT cap, title, language FROM legislation_docs WHERE cap=? AND language=?",
            (cap_norm, lang),
        ).fetchone()
        return {
            "found": False,
            "citation": f"Cap. {cap_norm} s.{section_norm}",
            "error": "section not found",
            "cap_found": bool(doc),
            "document_title": doc["title"] if doc else None,
        }
    item = _row_to_legislation(row, include_text=True, max_chars=max_chars)
    item["found"] = True
    item["document_title"] = row["title"]
    return item


def list_ordinances(
    conn: sqlite3.Connection,
    query: str | None = None,
    lang: str = "en",
    limit: int = 200,
) -> dict:
    lang = "en" if lang == "en" else "zh-Hant"
    sql = "SELECT cap, doc_type, doc_name, title, version_date, source_url FROM legislation_docs WHERE language=?"
    params: list = [lang]
    if query:
        sql += " AND (cap LIKE ? OR title LIKE ? OR doc_name LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like])
    sql += " ORDER BY cap LIMIT ?"
    params.append(max(1, min(limit, 500)))
    rows = conn.execute(sql, params).fetchall()
    return {
        "count": len(rows),
        "results": [dict(row) for row in rows],
    }


def verify_citation(
    conn: sqlite3.Connection,
    citation: str,
    lang: str = "en",
    live: bool = True,
) -> dict:
    """Verify a legislation or case citation against the corpus/HKLII."""
    leg = parse_legislation_citation(citation)
    if leg:
        if leg.section or leg.schedule:
            found = get_section(
                conn, leg.cap, leg.section or leg.schedule or "", lang, max_chars=4000
            )
            status = "verified" if found.get("found") else "not_found"
            return {
                "input": citation,
                "type": "legislation",
                "status": status,
                "parsed": leg.normalised,
                "details": found,
            }
        doc = conn.execute(
            "SELECT cap, title, version_date, source_url FROM legislation_docs "
            "WHERE cap=? AND language=?",
            (leg.cap, "en" if lang == "en" else "zh-Hant"),
        ).fetchone()
        return {
            "input": citation,
            "type": "legislation",
            "status": "verified" if doc else "not_found",
            "parsed": leg.normalised,
            "details": dict(doc) if doc else None,
        }

    case = parse_case_citation(citation)
    if case:
        normalised = case.normalised
        row = conn.execute(
            "SELECT neutral_citation, title, court, judgment_date FROM cases "
            "WHERE neutral_citation=? AND language=?",
            (normalised, "en" if lang == "en" else "zh-Hant"),
        ).fetchone()
        if row:
            return {
                "input": citation,
                "type": "case",
                "status": "verified",
                "parsed": normalised,
                "details": dict(row),
                "source": "local_cache",
            }
        if not live:
            return {
                "input": citation,
                "type": "case",
                "status": "unverified",
                "parsed": normalised,
                "details": None,
                "reason": "not cached and live retrieval disabled",
            }
        try:
            fetched = get_judgment(conn, normalised, lang=lang)
            matches = fetched.get("citation", "").upper() == normalised.upper()
            return {
                "input": citation,
                "type": "case",
                "status": "verified" if matches else "mismatch",
                "parsed": normalised,
                "details": {
                    "citation": fetched.get("citation"),
                    "title": fetched.get("title"),
                    "court": fetched.get("court"),
                    "judgment_date": fetched.get("judgment_date"),
                    "source_url": fetched.get("source_url"),
                },
                "source": "hklii_live",
            }
        except HKLIIError as exc:
            return {
                "input": citation,
                "type": "case",
                "status": "unverified",
                "parsed": normalised,
                "details": None,
                "reason": str(exc),
            }

    return {
        "input": citation,
        "type": "unknown",
        "status": "unrecognised",
        "reason": "Expected 'Cap. 221 s.9J' or '[2021] HKCFA 1'.",
    }
