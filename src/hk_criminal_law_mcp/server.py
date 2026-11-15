"""MCP server exposing Hong Kong criminal law research tools.

Run with:  python -m hk_criminal_law_mcp.server
"""

from __future__ import annotations

import sqlite3

try:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
except ImportError:  # MCP SDK 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _MCPServer

from .config import DISCLAIMER
from .db import connect, stats
from .hklii import get_case_paragraphs as _get_case_paragraphs
from .hklii import get_judgment, note_up as _note_up, search_cases as _search_cases
from .research import (
    authority_ranking as _authority_ranking,
    case_graph as _case_graph,
    doctrine_research as _doctrine_research,
    sentencing_research as _sentencing_research,
)
from .search import (
    get_section as _get_section,
    get_section_range as _get_section_range,
    get_statute_history as _get_statute_history,
    list_ordinances as _list_ordinances,
    list_section_versions as _list_section_versions,
    search_legislation as _search_legislation,
    verify_citation as _verify_citation,
    verify_citations as _verify_citations,
)

mcp = _MCPServer(
    "hk-criminal-law",
    instructions=(
        "Hong Kong criminal law and defence research. Every provision or judgment "
        "returned must be checked against the official source before use. This "
        "server is a retrieval aid, not a citator of record and not legal advice."
    ),
)


def _db() -> sqlite3.Connection:
    return connect()


def _ok(payload: dict) -> dict:
    payload.setdefault("disclaimer", DISCLAIMER)
    return payload


@mcp.tool()
def search_legislation(
    query: str,
    cap: str | None = None,
    lang: str = "en",
    limit: int = 8,
    include_text: bool = False,
    max_chars: int = 4000,
) -> dict:
    """Search the locally indexed Hong Kong e-Legislation corpus.

    Args:
        query: Words or a phrase, e.g. "bail conditions" or "合理懷疑".
        cap: Optional Cap number filter, e.g. "221" or "Cap. 221".
        lang: "en" (default) or "zh-Hant".
        limit: Maximum results (1-50).
        include_text: Include the full section text, not just a snippet.
    """
    conn = _db()
    try:
        return _ok(
            _search_legislation(conn, query, cap, lang, limit, include_text, max_chars)
        )
    finally:
        conn.close()


@mcp.tool()
def get_section(
    cap: str, section: str, lang: str = "en", max_chars: int = 20000
) -> dict:
    """Return a Hong Kong ordinance section or schedule with provenance.

    Args:
        cap: Cap number, e.g. "221" or "Cap. 221".
        section: Section number, e.g. "9J", "s9J", or "sch3".
        lang: "en" (default) or "zh-Hant".
        max_chars: Truncate very long sections/schedules to this many characters.
    """
    conn = _db()
    try:
        return _ok(_get_section(conn, cap, section, lang, max_chars))
    finally:
        conn.close()


@mcp.tool()
def get_section_range(
    cap: str,
    start: str,
    end: str,
    lang: str = "en",
    max_chars: int = 4000,
    limit: int = 100,
) -> dict:
    """Return all sections between two section numbers (inclusive).

    Example: Cap. 221 sections 9A to 9J. Section ordering handles numeric and
    letter suffixes. Parts/Orders may restart numbering; read the part context.
    """
    conn = _db()
    try:
        return _ok(
            _get_section_range(conn, cap, start, end, lang, max_chars, limit)
        )
    finally:
        conn.close()


@mcp.tool()
def statute_history(
    cap: str,
    section: str,
    as_of: str | None = None,
    lang: str = "en",
    max_chars: int = 20000,
) -> dict:
    """Return the provision text in force on a date (YYYY-MM-DD).

    Uses the official DATA.GOV.HK Past Version archives if ingested. If the
    historical corpus is unavailable, returns the current text with
    ``historical: false`` and an explicit warning.
    """
    conn = _db()
    try:
        return _ok(
            _get_statute_history(conn, cap, section, as_of, lang, max_chars)
        )
    finally:
        conn.close()


@mcp.tool()
def list_section_versions(cap: str, section: str, lang: str = "en") -> dict:
    """List all historical version dates available for a section."""
    conn = _db()
    try:
        return _ok(_list_section_versions(conn, cap, section, lang))
    finally:
        conn.close()


@mcp.tool()
def list_ordinances(query: str | None = None, lang: str = "en", limit: int = 200) -> dict:
    """List indexed ordinances/regulations, optionally filtered by title or Cap."""
    conn = _db()
    try:
        return _ok(_list_ordinances(conn, query, lang, limit))
    finally:
        conn.close()


@mcp.tool()
def search_cases(
    query: str,
    court: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 10,
    lang: str = "en",
    live: bool = True,
) -> dict:
    """Search Hong Kong judgments.

    Searches the local judgment cache first, then (unless live=False) HKLII's
    public search endpoint. `court` accepts a neutral-citation code such as
    HKCFA/HKCA/HKCFI/HKDC or a court name.
    """
    conn = _db()
    try:
        return _ok(
            _search_cases(
                conn, query, court, year_from, year_to, limit, lang, live
            )
        )
    finally:
        conn.close()


@mcp.tool()
def get_case(
    citation: str,
    lang: str = "en",
    paragraphs: list[str] | None = None,
    max_chars: int = 20000,
) -> dict:
    """Fetch a Hong Kong judgment by neutral citation and cache it locally.

    Args:
        citation: e.g. "[2021] HKCFA 1".
        lang: "en" or "zh-Hant".
        paragraphs: Optional paragraph numbers/ranges, e.g. ["12", "15-17"].
        max_chars: Truncate the returned full text to this many characters.
    """
    conn = _db()
    try:
        if paragraphs:
            return _ok(_get_case_paragraphs(conn, citation, paragraphs, lang))
        result = get_judgment(conn, citation, lang=lang)
        text = result.get("text") or ""
        if len(text) > max_chars:
            result["text"] = text[:max_chars]
            result["truncated"] = True
            result["full_text_chars"] = len(text)
        else:
            result["truncated"] = False
        return _ok(result)
    finally:
        conn.close()


@mcp.tool()
def get_case_paragraphs(citation: str, paragraphs: list[str], lang: str = "en") -> dict:
    """Return specific paragraphs of a judgment, fetching it if not cached."""
    conn = _db()
    try:
        return _ok(_get_case_paragraphs(conn, citation, paragraphs, lang))
    finally:
        conn.close()


@mcp.tool()
def note_up(citation: str, force: bool = False) -> dict:
    """Return HKLII note-up data for a judgment (research aid, not a citator)."""
    conn = _db()
    try:
        return _ok(_note_up(conn, citation, force=force))
    finally:
        conn.close()


@mcp.tool()
def verify_citation(citation: str, lang: str = "en", live: bool = True) -> dict:
    """Verify a legislation or case citation against the local corpus/HKLII.

    Examples: "Cap. 221 s.9J", "section 9J of Cap. 221", "[2021] HKCFA 1".
    """
    conn = _db()
    try:
        return _ok(_verify_citation(conn, citation, lang=lang, live=live))
    finally:
        conn.close()


@mcp.tool()
def verify_citations(text: str, lang: str = "en", live: bool = False) -> dict:
    """Extract and verify every citation in a passage.

    Defaults to local verification. Set live=True to fetch uncached judgments
    from HKLII.
    """
    conn = _db()
    try:
        return _ok(_verify_citations(conn, text, lang=lang, live=live))
    finally:
        conn.close()


@mcp.tool()
def doctrine_research(
    query: str,
    lang: str = "en",
    legislation_limit: int = 5,
    case_limit: int = 5,
    live_cases: bool = False,
) -> dict:
    """Return legislation hits and ranked case leads for a doctrine or issue.

    This is a discovery pack, not a legal answer. Fetch and read the judgments
    you intend to cite.
    """
    conn = _db()
    try:
        return _ok(
            _doctrine_research(
                conn, query, lang, legislation_limit, case_limit, live_cases
            )
        )
    finally:
        conn.close()


@mcp.tool()
def sentencing_research(
    cap: str,
    section: str,
    lang: str = "en",
    case_limit: int = 5,
    live_cases: bool = False,
) -> dict:
    """Return penalty text and sentencing case leads for an offence.

    Not a sentencing tariff. Extracts penalty language from the provision and
    searches for sentencing material in the case corpus.
    """
    conn = _db()
    try:
        return _ok(
            _sentencing_research(conn, cap, section, lang, case_limit, live_cases)
        )
    finally:
        conn.close()


@mcp.tool()
def authority_ranking(
    query: str,
    court: str | None = None,
    limit: int = 10,
    lang: str = "en",
    live: bool = False,
) -> dict:
    """Rank case results by court level and locally cached note-up data.

    Not a citator of record; check later treatment before relying on a case.
    """
    conn = _db()
    try:
        return _ok(
            _authority_ranking(conn, query, court, limit, lang, live)
        )
    finally:
        conn.close()


@mcp.tool()
def case_graph(
    citation: str,
    lang: str = "en",
    live_note_up: bool = True,
) -> dict:
    """Return outgoing cited cases and incoming note-up citations for a case."""
    conn = _db()
    try:
        return _ok(_case_graph(conn, citation, lang, live_note_up))
    finally:
        conn.close()


@mcp.tool()
def corpus_status() -> dict:
    """Report database size, coverage, and last ingest/fetch times."""
    conn = _db()
    try:
        return _ok({"status": "ok", "corpus": stats(conn)})
    finally:
        conn.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
