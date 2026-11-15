"""Composite research helpers built on the local corpus and HKLII cache."""

from __future__ import annotations

import json
import re
import sqlite3

from .citations import parse_case_citation
from .hklii import get_judgment, note_up, search_cases
from .search import get_section, search_legislation

COURT_LEVEL = {
    "hkcfa": 5,
    "hkca": 4,
    "hkcfi": 3,
    "hkdc": 2,
    "hkmagc": 1,
    "hkct": 2,
    "hkfc": 2,
    "hkldt": 2,
    "hksct": 1,
    "hkcrc": 1,
    "hkoat": 1,
    "hklat": 1,
}

COURT_LABEL = {
    5: "Court of Final Appeal",
    4: "Court of Appeal",
    3: "Court of First Instance",
    2: "District Court / specialist tribunal",
    1: "Magistrates / lower tribunal",
    0: "Unranked",
}

_PENALTY_RE = re.compile(
    r"(liable|penalt|imprison|fine|sentenc|conviction|years?|months?|HKD|\$|"
    r"罰款|監禁|刑罰|定罪|判刑|年|月)",
    re.I,
)


def _court_key(item: dict) -> str:
    key = (item.get("court_abbr") or item.get("court_code") or "").lower()
    if key:
        return key
    citation = item.get("citation") or ""
    parsed = parse_case_citation(citation)
    return parsed.court_abbr if parsed and parsed.court_abbr else ""


def _court_level(item: dict) -> int:
    return COURT_LEVEL.get(_court_key(item), 0)


def _cached_incoming_count(conn: sqlite3.Connection, citation: str) -> int:
    """Count note-up rows in the local cache that cite ``citation``."""
    count = 0
    for row in conn.execute("SELECT payload FROM case_noteups"):
        try:
            payload = json.loads(row["payload"] or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, list):
            continue
        for item in payload:
            if isinstance(item, dict) and item.get("neutral") == citation:
                count += 1
                break
    return count


def doctrine_research(
    conn: sqlite3.Connection,
    query: str,
    lang: str = "en",
    legislation_limit: int = 5,
    case_limit: int = 5,
    live_cases: bool = False,
) -> dict:
    """Return legislation hits and ranked case leads for a doctrine/issue.

    This is a discovery pack, not an answer. It does not fetch every judgment;
    use ``get_case_paragraphs`` on the leads you intend to cite.
    """
    legislation = search_legislation(
        conn, query, lang=lang, limit=legislation_limit
    )
    cases = search_cases(
        conn, query, lang=lang, limit=case_limit, live=live_cases
    )
    ranked = []
    for item in cases.get("results", []):
        level = _court_level(item)
        ranked.append(
            {
                **item,
                "court_level": level,
                "court_level_label": COURT_LABEL.get(level, "Unranked"),
                "authority_rank": (level, item.get("year") or 0),
            }
        )
    ranked.sort(key=lambda item: item["authority_rank"], reverse=True)
    return {
        "query": query,
        "legislation": {
            "count": legislation.get("count", 0),
            "results": legislation.get("results", []),
        },
        "cases": {
            "count": cases.get("count", 0),
            "local_count": cases.get("local_count", 0),
            "results": ranked,
            "live_source": cases.get("live_source"),
        },
        "next_steps": [
            "Run verify_citation on every lead before relying on it.",
            "Fetch the judgment with get_case and read the paragraph with get_case_paragraphs.",
            "Use note_up to check later treatment; it is a research aid, not a citator of record.",
            "Read the full provision, including definitions and any statutory defence.",
        ],
        "warning": (
            "Discovery pack only. Search ranking is not legal authority; read the "
            "judgment and the provision in context."
        ),
    }


def _penalty_excerpts(text: str, limit: int = 6) -> list[str]:
    chunks = re.split(r"(?<=[.;。；])\s+|\n+", text or "")
    hits = [
        re.sub(r"\s+", " ", chunk).strip()
        for chunk in chunks
        if chunk.strip() and _PENALTY_RE.search(chunk)
    ]
    # Prefer sentences that look like a penalty, then keep the first few.
    hits.sort(key=lambda chunk: (0 if "liable" in chunk.lower() else 1, len(chunk)))
    return hits[:limit]


def sentencing_research(
    conn: sqlite3.Connection,
    cap: str,
    section: str,
    lang: str = "en",
    case_limit: int = 5,
    live_cases: bool = False,
) -> dict:
    """Return the penalty text plus sentencing case leads for an offence.

    This is **not** a sentencing tariff. It extracts penalty language from the
    provision and searches the case corpus for sentencing material.
    """
    provision = get_section(conn, cap, section, lang=lang, max_chars=12000)
    if not provision.get("found"):
        return {
            "found": False,
            "error": "section not found",
            "citation": provision.get("citation"),
        }

    heading = provision.get("heading") or f"Cap. {cap} s.{section}"
    query = f"{heading} sentencing" if lang == "en" else f"{heading} 判刑"
    cases = search_cases(
        conn, query, lang=lang, limit=case_limit, live=live_cases
    )
    ranked = []
    for item in cases.get("results", []):
        level = _court_level(item)
        ranked.append(
            {
                **item,
                "court_level": level,
                "court_level_label": COURT_LABEL.get(level, "Unranked"),
            }
        )
    ranked.sort(
        key=lambda item: (item.get("court_level", 0), item.get("year") or 0),
        reverse=True,
    )
    return {
        "found": True,
        "provision": {
            "citation": provision.get("citation"),
            "heading": provision.get("heading"),
            "document_title": provision.get("document_title"),
            "version_date": provision.get("version_date"),
            "source_url": provision.get("source_url"),
            "text": provision.get("text"),
            "truncated": provision.get("truncated", False),
        },
        "penalty_excerpts": _penalty_excerpts(provision.get("text") or ""),
        "cases": {
            "count": cases.get("count", 0),
            "results": ranked,
            "live_source": cases.get("live_source"),
        },
        "next_steps": [
            "Read the full offence provision and any related subsidiary legislation.",
            "Retrieve the sentencing judgments and read the relevant paragraphs.",
            "Check the current guideline/tariff authorities and any later treatment.",
            "Apply totality, parity, plea timing and personal mitigation to the facts.",
        ],
        "warning": (
            "Not a sentencing tariff. Penalty excerpts are extracted from the "
            "current provision; sentencing is fact-specific and guideline-driven. "
            "Verify the current authorities before advising."
        ),
    }


def authority_ranking(
    conn: sqlite3.Connection,
    query: str,
    court: str | None = None,
    limit: int = 10,
    lang: str = "en",
    live: bool = False,
) -> dict:
    """Rank case search results by court level and cached incoming citations.

    The incoming-citation component only sees note-up data already cached
    locally; it is not a citator of record.
    """
    cases = search_cases(
        conn,
        query,
        court=court,
        limit=max(limit * 2, 20),
        lang=lang,
        live=live,
    )
    ranked = []
    for item in cases.get("results", []):
        level = _court_level(item)
        incoming = _cached_incoming_count(conn, item.get("citation") or "")
        score = level * 1000 + incoming * 50 + (item.get("year") or 0)
        ranked.append(
            {
                **item,
                "court_level": level,
                "court_level_label": COURT_LABEL.get(level, "Unranked"),
                "cached_incoming_citations": incoming,
                "score": score,
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {
        "query": query,
        "count": len(ranked[: max(1, min(limit, 50))]),
        "results": ranked[: max(1, min(limit, 50))],
        "warning": (
            "Ranking uses court level, year and locally cached note-up data. It is "
            "not a citator of record; check later treatment before relying on a case."
        ),
    }


def case_graph(
    conn: sqlite3.Connection,
    citation: str,
    lang: str = "en",
    live_note_up: bool = True,
) -> dict:
    """Return outgoing cited cases and incoming note-up citations for a case."""
    case = get_judgment(conn, citation, lang=lang)
    outgoing = case.get("cited_cases") or []
    incoming = []
    warning = None
    if live_note_up:
        try:
            payload = note_up(conn, citation).get("payload")
            if isinstance(payload, list):
                incoming = payload
        except Exception as exc:  # network/service failure
            warning = f"note-up unavailable: {exc}"
    return {
        "citation": case.get("citation"),
        "title": case.get("title"),
        "court": case.get("court"),
        "judgment_date": case.get("judgment_date"),
        "source_url": case.get("source_url"),
        "outgoing": outgoing,
        "outgoing_count": len(outgoing),
        "incoming": incoming,
        "incoming_count": len(incoming),
        "warning": warning
        or (
            "Outgoing citations come from HKLII's judgment metadata; incoming "
            "citations come from HKLII note-up. Neither is a citator of record."
        ),
    }
