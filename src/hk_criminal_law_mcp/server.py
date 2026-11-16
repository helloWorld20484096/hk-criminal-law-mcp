"""MCP server exposing Hong Kong criminal law research tools.

Run with:  python -m hk_criminal_law_mcp.server
"""

from __future__ import annotations

import sqlite3

from mcp.types import ToolAnnotations

try:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
except ImportError:  # MCP SDK 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _MCPServer

from .config import DISCLAIMER, live_case_default
from .db import connect, stats
from .doj import (
    doj_status as _doj_status,
    get_doj_document as _get_doj_document,
    list_doj_documents as _list_doj_documents,
    search_doj as _search_doj,
    sync_doj as _sync_doj,
    verify_doj_citation as _verify_doj_citation,
)
from .hklii import get_case_paragraphs as _get_case_paragraphs
from .hklii import get_judgment, note_up as _note_up, search_cases as _search_cases
from .research import (
    authority_ranking as _authority_ranking,
    case_graph as _case_graph,
    doctrine_research as _doctrine_research,
    sentencing_research as _sentencing_research,
)
from .sync import sync_status as _sync_status
from .semantic_index import get_index as _get_semantic_index
from .semantic_index import index_error as _semantic_index_error
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

INSTRUCTIONS = (
    "Hong Kong criminal law and defence research. Case search/read follows the "
    "deployment: local-only when HK_LAW_LOCAL_ONLY=1, otherwise live HKLII "
    "query-time access with a local fallback; live access remains subject to "
    "the source's terms. Agent protocol: call corpus_status or sync_status "
    "first; search the DOJ Prosecution Code and prosecution policies with "
    "search_doj and read them with get_doj_document; use semantic_search and "
    "semantic_neighbors for discovery, then get_section, statute_history, "
    "search_cases, and get_case_paragraphs for primary text; run "
    "verify_citations (and verify_doj for DOJ policy citations) before relying "
    "on anything; label anything unverified [UNVERIFIED]. The semantic atlas "
    "is a discovery aid, not authority. This server is a retrieval aid, not a "
    "citator of record and not legal advice."
)

mcp = _MCPServer("hk-criminal-law", instructions=INSTRUCTIONS)

# Tool annotations are hints for clients (notably ChatGPT, which prompts before
# write-like tools). The research tools do not change the caller's environment;
# only sync_doj updates the local corpus. "Live" tools may contact HKLII.
READ_LOCAL = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
READ_LIVE = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)
WRITE_LIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


def _db() -> sqlite3.Connection:
    return connect()


def _ok(payload: dict) -> dict:
    payload.setdefault("disclaimer", DISCLAIMER)
    return payload


@mcp.tool(annotations=READ_LOCAL)
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


@mcp.tool(annotations=READ_LOCAL)
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


@mcp.tool(annotations=READ_LOCAL)
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


@mcp.tool(annotations=READ_LOCAL)
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


@mcp.tool(annotations=READ_LOCAL)
def list_section_versions(cap: str, section: str, lang: str = "en") -> dict:
    """List all historical version dates available for a section."""
    conn = _db()
    try:
        return _ok(_list_section_versions(conn, cap, section, lang))
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def list_ordinances(query: str | None = None, lang: str = "en", limit: int = 200) -> dict:
    """List indexed ordinances/regulations, optionally filtered by title or Cap."""
    conn = _db()
    try:
        return _ok(_list_ordinances(conn, query, lang, limit))
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def search_cases(
    query: str,
    court: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 10,
    lang: str = "en",
    live: bool | None = None,
) -> dict:
    """Search Hong Kong judgments.

    The default follows ``HK_LAW_LOCAL_ONLY``: local-only when set to 1 (the
    public launcher default), live HKLII search when set to 0. Live search is
    for query-time coverage and remains subject to HKLII's terms.
    `court` accepts a neutral-citation code such as HKCFA/HKCA/HKCFI/HKDC.
    """
    if live is None:
        live = live_case_default()
    conn = _db()
    try:
        return _ok(
            _search_cases(
                conn, query, court, year_from, year_to, limit, lang, live
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def get_case(
    citation: str,
    lang: str = "en",
    paragraphs: list[str] | None = None,
    max_chars: int = 20000,
    allow_live: bool | None = None,
) -> dict:
    """Read a Hong Kong judgment, local by default.

    Args:
        citation: e.g. "[2021] HKCFA 1".
        lang: "en" or "zh-Hant".
        paragraphs: Optional paragraph numbers/ranges, e.g. ["12", "15-17"].
        max_chars: Truncate the returned full text to this many characters.
        allow_live: Defaults to ``HK_LAW_LOCAL_ONLY=0`` (live when local-only is
            off); otherwise a missing case is a coverage gap, not an error to
            paper over.
    """
    if allow_live is None:
        allow_live = live_case_default()
    conn = _db()
    try:
        if paragraphs:
            return _ok(
                _get_case_paragraphs(
                    conn, citation, paragraphs, lang, allow_live=allow_live
                )
            )
        result = get_judgment(conn, citation, lang=lang, allow_live=allow_live)
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


@mcp.tool(annotations=READ_LIVE)
def get_case_paragraphs(
    citation: str,
    paragraphs: list[str],
    lang: str = "en",
    allow_live: bool | None = None,
) -> dict:
    """Return specific paragraphs, local by default.

    ``allow_live`` follows ``HK_LAW_LOCAL_ONLY`` just like :func:`get_case`.
    """
    if allow_live is None:
        allow_live = live_case_default()
    conn = _db()
    try:
        return _ok(
            _get_case_paragraphs(
                conn, citation, paragraphs, lang, allow_live=allow_live
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def note_up(
    citation: str, force: bool = False, allow_live: bool | None = None
) -> dict:
    """Return note-up data (research aid, not a citator).

    ``allow_live`` follows ``HK_LAW_LOCAL_ONLY``; the public default uses the
    cache only.
    """
    if allow_live is None:
        allow_live = live_case_default()
    conn = _db()
    try:
        return _ok(
            _note_up(conn, citation, force=force, allow_live=allow_live)
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def verify_citation(
    citation: str, lang: str = "en", live: bool | None = None
) -> dict:
    """Verify a citation against the corpus.

    ``live`` follows ``HK_LAW_LOCAL_ONLY``; the public default is local.
    Examples: "Cap. 221 s.9J", "section 9J of Cap. 221", "[2021] HKCFA 1".
    """
    if live is None:
        live = live_case_default()
    conn = _db()
    try:
        return _ok(_verify_citation(conn, citation, lang=lang, live=live))
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def verify_citations(
    text: str, lang: str = "en", live: bool | None = None
) -> dict:
    """Extract and verify every citation in a passage.

    ``live`` follows ``HK_LAW_LOCAL_ONLY``; the public default is local.
    """
    if live is None:
        live = live_case_default()
    conn = _db()
    try:
        return _ok(_verify_citations(conn, text, lang=lang, live=live))
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def doctrine_research(
    query: str,
    lang: str = "en",
    legislation_limit: int = 5,
    case_limit: int = 5,
    live_cases: bool | None = None,
) -> dict:
    """Return legislation hits and ranked case leads for a doctrine or issue.

    ``live_cases`` follows ``HK_LAW_LOCAL_ONLY``; the public release can opt
    into local-only. This is a discovery pack, not a legal answer. Fetch and
    read the judgments you intend to cite.
    """
    if live_cases is None:
        live_cases = live_case_default()
    conn = _db()
    try:
        return _ok(
            _doctrine_research(
                conn, query, lang, legislation_limit, case_limit, live_cases
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def sentencing_research(
    cap: str,
    section: str,
    lang: str = "en",
    case_limit: int = 5,
    live_cases: bool | None = None,
) -> dict:
    """Return penalty text and sentencing case leads for an offence.

    ``live_cases`` follows ``HK_LAW_LOCAL_ONLY``. Not a sentencing tariff.
    Extracts penalty language from the provision and searches for sentencing
    material in the case corpus.
    """
    if live_cases is None:
        live_cases = live_case_default()
    conn = _db()
    try:
        return _ok(
            _sentencing_research(conn, cap, section, lang, case_limit, live_cases)
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def authority_ranking(
    query: str,
    court: str | None = None,
    limit: int = 10,
    lang: str = "en",
    live: bool | None = None,
) -> dict:
    """Rank case results by court level and note-up data.

    ``live`` follows ``HK_LAW_LOCAL_ONLY``. Not a citator of record; check
    later treatment before relying on a case.
    """
    if live is None:
        live = live_case_default()
    conn = _db()
    try:
        return _ok(
            _authority_ranking(conn, query, court, limit, lang, live)
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LIVE)
def case_graph(
    citation: str,
    lang: str = "en",
    live_note_up: bool | None = None,
) -> dict:
    """Return outgoing cited cases and incoming note-up citations.

    ``live_note_up`` follows ``HK_LAW_LOCAL_ONLY``; the public default uses the
    local cache.
    """
    if live_note_up is None:
        live_note_up = live_case_default()
    conn = _db()
    try:
        return _ok(_case_graph(conn, citation, lang, live_note_up))
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def corpus_status() -> dict:
    """Report database size, coverage, sync freshness, and local-only mode."""
    conn = _db()
    try:
        return _ok({"status": "ok", "corpus": _sync_status(conn)})
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def sync_status() -> dict:
    """Report local coverage, last sync runs, and permission configuration."""
    conn = _db()
    try:
        return _ok(_sync_status(conn))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Department of Justice (DOJ) publications
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_LOCAL)
def search_doj(
    query: str,
    category: str | None = None,
    lang: str = "en",
    limit: int = 8,
    include_text: bool = False,
    max_chars: int = 4000,
) -> dict:
    """Search the DOJ Prosecution Code and prosecution policies.

    The local DOJ corpus covers the Prosecution Code and the domestic-violence
    prosecution policy. ``category`` is ``prosecution_code`` or
    ``domestic_violence``. This is policy material, not legislation; read the
    full page before relying on a paragraph.
    """
    conn = _db()
    try:
        return _ok(
            _search_doj(
                conn,
                query,
                category=category,
                language=lang,
                limit=limit,
                include_text=include_text,
                max_chars=max_chars,
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def get_doj_document(
    slug: str,
    lang: str = "en",
    paragraphs: list[str] | None = None,
    max_chars: int = 20000,
) -> dict:
    """Read a DOJ publication by slug, e.g. ``prosecution_ch5``.

    Args:
        slug: e.g. ``prosecution_ch5`` or ``domesticviolence_11``.
        lang: ``en`` or ``zh-Hant``.
        paragraphs: Optional paragraph numbers/ranges, e.g. ``["5.9"]`` or
            ``["14-17"]``.
        max_chars: Truncate the full text to this many characters.
    """
    conn = _db()
    try:
        return _ok(
            _get_doj_document(
                conn,
                slug,
                language=lang,
                paragraphs=paragraphs,
                max_chars=max_chars,
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def list_doj_documents(
    category: str | None = None, lang: str = "en", limit: int = 200
) -> dict:
    """List indexed DOJ publications and their paragraph counts."""
    conn = _db()
    try:
        return _ok(
            _list_doj_documents(
                conn, category=category, language=lang, limit=limit
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def verify_doj(
    citation: str, category: str | None = None, lang: str = "en"
) -> dict:
    """Verify a DOJ policy citation, e.g. ``Prosecution Code §5.9``.

    This checks the local DOJ corpus only. It is not a citator and does not
    verify that the paragraph supports a proposition.
    """
    conn = _db()
    try:
        return _ok(
            _verify_doj_citation(
                conn, citation, category=category, language=lang
            )
        )
    finally:
        conn.close()


@mcp.tool(annotations=READ_LOCAL)
def doj_status() -> dict:
    """Report DOJ corpus coverage, freshness and provenance."""
    conn = _db()
    try:
        return _ok(_doj_status(conn))
    finally:
        conn.close()


@mcp.tool(annotations=WRITE_LIVE)
def sync_doj(force: bool = False, lang: str = "en") -> dict:
    """Incrementally update the local DOJ corpus.

    Fetches the curated Prosecution Code and domestic-violence policy pages
    (plus bounded discovery from their index pages), using conditional GETs and
    checksums. It is polite and may take 20–60 seconds. The full daily update is
    also available as ``hk-law sync-doj``.
    """
    conn = _db()
    try:
        result = _sync_doj(conn, force=force, language=lang)
        return _ok({**result, "corpus": _doj_status(conn)})
    finally:
        conn.close()


def _semantic_payload(index):
    if index is not None:
        return index, None
    return None, {
        "available": False,
        "error": _semantic_index_error() or "Semantic atlas data is not available.",
        "build": (
            "Run `make map-all` in the repository and set HK_LAW_SEMANTIC_MAP "
            "to semantic_map/dist/data."
        ),
    }


@mcp.tool(annotations=READ_LOCAL)
def semantic_status() -> dict:
    """Report whether the semantic atlas is available and what it covers."""
    index, error = _semantic_payload(_get_semantic_index())
    if index is None:
        return _ok(error)
    return _ok(index.status())


@mcp.tool(annotations=READ_LOCAL)
def semantic_search(
    query: str,
    limit: int = 10,
    cluster: str | int | None = None,
    language: str | None = None,
) -> dict:
    """Search the semantic atlas's citation/heading index for provisions.

    This is a metadata/keyword lookup over the generated atlas; use
    `semantic_neighbors` for nearest-neighbour discovery. `cluster` accepts a
    cluster id or a label fragment; `language` is `en` or `zh-Hant`. Read the
    provision with `get_section` and verify it with `verify_citation` before
    relying on it.
    """
    index, error = _semantic_payload(_get_semantic_index())
    if index is None:
        return _ok(error)
    return _ok(index.search(query, limit=limit, cluster=cluster, language=language))


@mcp.tool(annotations=READ_LOCAL)
def semantic_locate(citation: str, language: str | None = None) -> dict:
    """Find a legislation citation's point(s) and cluster in the semantic atlas."""
    index, error = _semantic_payload(_get_semantic_index())
    if index is None:
        return _ok(error)
    return _ok(index.locate(citation, language=language))


@mcp.tool(annotations=READ_LOCAL)
def semantic_neighbors(
    point_id: int | None = None,
    citation: str | None = None,
    language: str | None = None,
    limit: int = 10,
) -> dict:
    """Return provisions nearest to a point or citation in the semantic atlas.

    Similarity is semantic, not authority or treatment. Verify every result with
    `get_section` and `verify_citation`.
    """
    index, error = _semantic_payload(_get_semantic_index())
    if index is None:
        return _ok(error)
    return _ok(
        index.neighbors(
            point_id=point_id,
            citation=citation,
            language=language,
            limit=limit,
        )
    )


@mcp.tool(annotations=READ_LOCAL)
def semantic_clusters(query: str | None = None, limit: int = 50) -> dict:
    """List semantic-atlas topics, optionally filtered by label or Cap. title."""
    index, error = _semantic_payload(_get_semantic_index())
    if index is None:
        return _ok(error)
    return _ok(index.clusters_list(query=query, limit=limit))


@mcp.tool(annotations=READ_LOCAL)
def semantic_cluster(cluster_id: int, limit: int = 20) -> dict:
    """Show one semantic topic and representative member provisions."""
    index, error = _semantic_payload(_get_semantic_index())
    if index is None:
        return _ok(error)
    return _ok(index.cluster(cluster_id, limit=limit))


# The same functions back the stdio MCP server, the remote HTTP MCP endpoint,
# the JSON API and the mobile web app. Keep this table in step with the
# @mcp.tool() definitions above; tests/test_http_server.py enforces that it
# matches the tools registered on ``mcp``.
TOOL_FUNCTIONS = {
    "search_legislation": search_legislation,
    "get_section": get_section,
    "get_section_range": get_section_range,
    "statute_history": statute_history,
    "list_section_versions": list_section_versions,
    "list_ordinances": list_ordinances,
    "search_cases": search_cases,
    "get_case": get_case,
    "get_case_paragraphs": get_case_paragraphs,
    "note_up": note_up,
    "verify_citation": verify_citation,
    "verify_citations": verify_citations,
    "doctrine_research": doctrine_research,
    "sentencing_research": sentencing_research,
    "authority_ranking": authority_ranking,
    "case_graph": case_graph,
    "corpus_status": corpus_status,
    "sync_status": sync_status,
    "search_doj": search_doj,
    "get_doj_document": get_doj_document,
    "list_doj_documents": list_doj_documents,
    "verify_doj": verify_doj,
    "doj_status": doj_status,
    "sync_doj": sync_doj,
    "semantic_status": semantic_status,
    "semantic_search": semantic_search,
    "semantic_locate": semantic_locate,
    "semantic_neighbors": semantic_neighbors,
    "semantic_clusters": semantic_clusters,
    "semantic_cluster": semantic_cluster,
}

LIVE_TOOLS = {
    "search_cases",
    "get_case",
    "get_case_paragraphs",
    "note_up",
    "verify_citation",
    "verify_citations",
    "doctrine_research",
    "sentencing_research",
    "authority_ranking",
    "case_graph",
}

TOOL_ANNOTATIONS = {
    name: (
        WRITE_LIVE
        if name == "sync_doj"
        else READ_LIVE
        if name in LIVE_TOOLS
        else READ_LOCAL
    )
    for name in TOOL_FUNCTIONS
}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
