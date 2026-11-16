"""Search and citation-verification helpers over the local corpus."""

from __future__ import annotations

import re
import sqlite3

from .citations import (
    LegislationCitation,
    extract_citations,
    normalise_cap,
    normalise_section,
    parse_case_citation,
    parse_legislation_citation,
)
from .hklii import CaseNotLocalError, HKLIIError, get_judgment

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


def section_sort_key(value: str) -> tuple:
    """Sort section numbers like 9, 9A, 9J, 23, sch3."""
    norm = normalise_section(value)
    if norm.lower().startswith("sch"):
        return (1_000_000, norm, "")
    match = re.match(r"^(\d+)([A-Za-z]*)(.*)$", norm)
    if match:
        return (int(match.group(1)), match.group(2).upper(), match.group(3))
    return (10_000_000, norm, "")


def _section_candidates(section: str) -> set[str]:
    norm = normalise_section(section)
    return {norm, f"s{norm}", f"sch{norm}"}


def list_section_versions(
    conn: sqlite3.Connection,
    cap: str,
    section: str,
    lang: str = "en",
) -> dict:
    """List every historical version date available for a section."""
    lang = "en" if lang == "en" else "zh-Hant"
    cap_norm = normalise_cap(cap)
    candidates = sorted(_section_candidates(section))
    placeholders = ",".join("?" for _ in candidates)
    rows = conn.execute(
        f"""
        SELECT d.version_date, s.heading, s.section_key, s.section_no
        FROM legislation_history_sections s
        JOIN legislation_history_docs d ON d.id = s.doc_id
        WHERE s.cap = ? AND s.language = ?
          AND (s.section_no IN ({placeholders}) COLLATE NOCASE
               OR s.section_key IN ({placeholders}) COLLATE NOCASE)
        ORDER BY d.version_date
        """,
        [cap_norm, lang, *candidates, *candidates],
    ).fetchall()
    return {
        "cap": cap_norm,
        "section": normalise_section(section),
        "language": lang,
        "count": len(rows),
        "versions": [dict(row) for row in rows],
        "warning": (
            "Historical coverage depends on the DATA.GOV.HK Past Version archives "
            "being downloaded and ingested."
        ),
    }


def get_statute_history(
    conn: sqlite3.Connection,
    cap: str,
    section: str,
    as_of: str | None = None,
    lang: str = "en",
    max_chars: int = 20000,
) -> dict:
    """Return the provision text in force on a given date.

    Uses the official Past Version archives. If no historical version is
    available, returns the current section with ``historical: false`` rather
    than pretending it is the historical text.
    """
    from datetime import date as _date

    lang = "en" if lang == "en" else "zh-Hant"
    cap_norm = normalise_cap(cap)
    section_norm = normalise_section(section)
    requested = as_of or _date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested):
        return {
            "found": False,
            "error": "as_of must be YYYY-MM-DD",
            "requested_date": requested,
            "citation": f"Cap. {cap_norm} s.{section_norm}",
        }

    candidates = sorted(_section_candidates(section))
    placeholders = ",".join("?" for _ in candidates)

    current = get_section(conn, cap_norm, section, lang, max_chars=max_chars)
    current_version = (current.get("version_date") or "")[:10] if current.get("found") else ""
    if current.get("found") and current_version and requested >= current_version:
        current["historical"] = False
        current["current"] = True
        current["requested_date"] = requested
        current["historical_available"] = True
        current["warning"] = (
            "The requested date is on or after the current version date "
            f"({current_version}); the current text is returned. Use an earlier "
            "date to retrieve a historical version."
        )
        return current

    row = conn.execute(
        f"""
        SELECT s.*, d.version_date AS doc_version_date,
               d.title AS document_title, d.source_url AS doc_source_url
        FROM legislation_history_sections s
        JOIN legislation_history_docs d ON d.id = s.doc_id
        WHERE s.cap = ? AND s.language = ?
          AND (s.section_no IN ({placeholders}) COLLATE NOCASE
               OR s.section_key IN ({placeholders}) COLLATE NOCASE)
          AND d.version_date <= ?
        ORDER BY d.version_date DESC
        LIMIT 1
        """,
        [cap_norm, lang, *candidates, *candidates, requested],
    ).fetchone()

    next_row = None
    if row:
        next_row = conn.execute(
            f"""
            SELECT d.version_date
            FROM legislation_history_sections s
            JOIN legislation_history_docs d ON d.id = s.doc_id
            WHERE s.cap = ? AND s.language = ?
              AND (s.section_no IN ({placeholders}) COLLATE NOCASE
                   OR s.section_key IN ({placeholders}) COLLATE NOCASE)
              AND d.version_date > ?
            ORDER BY d.version_date ASC
            LIMIT 1
            """,
            [cap_norm, lang, *candidates, *candidates, requested],
        ).fetchone()

    if not row:
        has_history = conn.execute(
            f"""
            SELECT 1 FROM legislation_history_sections
            WHERE cap = ? AND language = ?
              AND (section_no IN ({placeholders}) COLLATE NOCASE
                   OR section_key IN ({placeholders}) COLLATE NOCASE)
            LIMIT 1
            """,
            [cap_norm, lang, *candidates, *candidates],
        ).fetchone()
        if current.get("found"):
            current["historical"] = False
            current["requested_date"] = requested
            current["historical_available"] = bool(has_history)
            if has_history:
                current["warning"] = (
                    "No historical version dated on or before the requested date "
                    "is available. The current-version text is returned instead; "
                    "do not treat it as the law in force on the requested date."
                )
            else:
                current["warning"] = (
                    "No historical version is available for this section in the "
                    "local corpus. The current-version text is returned instead; "
                    "do not treat it as the law in force on the requested date. "
                    "Download and ingest the DATA.GOV.HK Past Version archives."
                )
            return current
        return {
            "found": False,
            "error": "section not found in historical or current corpus",
            "citation": f"Cap. {cap_norm} s.{section_norm}",
            "requested_date": requested,
            "historical_available": bool(has_history),
        }

    text = row["text"] or ""
    truncated = len(text) > max_chars
    item = {
        "found": True,
        "historical": True,
        "citation": _section_citation(row["cap"], row["section_no"] or row["section_key"]),
        "cap": row["cap"],
        "section": row["section_no"],
        "heading": row["heading"],
        "part": row["part"],
        "division": row["division"],
        "language": row["language"],
        "version_date": row["doc_version_date"],
        "requested_date": requested,
        "document_title": row["document_title"],
        "source_url": row["doc_source_url"],
        "source_note": row["source_note"],
        "text": text[:max_chars],
        "truncated": truncated,
        "full_length": len(text),
        "next_version_date": next_row["version_date"] if next_row else None,
        "warning": (
            "This is the version in force on the requested date according to the "
            "official Past Version archive. Check commencement and any later "
            "amendment before relying on it."
        ),
    }
    if next_row:
        item["later_version_warning"] = (
            f"A later version dated {next_row['version_date']} exists. The text "
            "above is not the current law."
        )
    return item


def get_section_range(
    conn: sqlite3.Connection,
    cap: str,
    start: str,
    end: str,
    lang: str = "en",
    max_chars: int = 4000,
    limit: int = 100,
) -> dict:
    """Return all sections between start and end (inclusive) for a Cap."""
    lang = "en" if lang == "en" else "zh-Hant"
    cap_norm = normalise_cap(cap)
    start_key = section_sort_key(start)
    end_key = section_sort_key(end)
    if end_key < start_key:
        start_key, end_key = end_key, start_key

    rows = conn.execute(
        """
        SELECT s.*, d.title AS document_title
        FROM legislation_sections s
        JOIN legislation_docs d ON d.id = s.doc_id
        WHERE s.cap = ? AND s.language = ?
        """,
        (cap_norm, lang),
    ).fetchall()

    matched = [
        row
        for row in rows
        if start_key <= section_sort_key(row["section_no"] or row["section_key"]) <= end_key
    ]
    matched.sort(key=lambda r: section_sort_key(r["section_no"] or r["section_key"]))
    total = len(matched)
    results = []
    for row in matched[: max(1, min(limit, 500))]:
        item = _row_to_legislation(row, include_text=True, max_chars=max_chars)
        item["document_title"] = row["document_title"]
        results.append(item)
    return {
        "cap": cap_norm,
        "start": normalise_section(start),
        "end": normalise_section(end),
        "language": lang,
        "count": len(results),
        "total_matched": total,
        "truncated": total > len(results),
        "results": results,
        "warning": (
            "Section ordering is by number/letter. Parts and Orders can restart "
            "numbering; read the part/division context and the full text."
        ),
    }


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


def verify_citations(
    conn: sqlite3.Connection,
    text: str,
    lang: str = "en",
    live: bool = False,
) -> dict:
    """Extract and verify every citation in a passage.

    ``live=False`` (the default) verifies cases only if cached; legislation is
    verified locally. Set ``live=True`` to fetch uncached judgments from HKLII.
    """
    matches = extract_citations(text)
    summary = {
        "total": len(matches),
        "verified": 0,
        "not_found": 0,
        "unverified": 0,
        "mismatch": 0,
        "unrecognised": 0,
    }
    results = []
    for match in matches:
        result = verify_citation(conn, match.normalised, lang=lang, live=live)
        status = result.get("status", "unrecognised")
        if status in summary:
            summary[status] += 1
        results.append(
            {
                "raw": match.raw,
                "normalised": match.normalised,
                "kind": match.kind,
                "start": match.start,
                "end": match.end,
                "status": status,
                "result": result,
            }
        )
    summary["all_verified"] = summary["total"] > 0 and summary["verified"] == summary["total"]
    return {
        "summary": summary,
        "citations": results,
        "warning": (
            "A verified citation exists in the corpus; that does not by itself "
            "establish that it supports the proposition. Read the provision or "
            "paragraph in context."
        ),
    }


def verify_citation(
    conn: sqlite3.Connection,
    citation: str,
    lang: str = "en",
    live: bool = False,
) -> dict:
    """Verify a legislation or case citation against the local corpus."""
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
        except (HKLIIError, CaseNotLocalError) as exc:
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
