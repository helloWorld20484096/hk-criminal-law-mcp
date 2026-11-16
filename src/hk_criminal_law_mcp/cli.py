"""Command-line interface for the HK criminal law corpus and MCP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import db_path, DISCLAIMER
from .db import connect, stats
from .doj import (
    doj_status,
    get_doj_document,
    list_doj_documents,
    search_doj,
    sync_doj,
    verify_doj_citation,
)
from .hklii import get_case_paragraphs, get_judgment, note_up, search_cases
from .ingest_legislation import (
    download_archives,
    ingest_archives,
    is_history_archive,
)
from .research import (
    authority_ranking,
    case_graph,
    doctrine_research,
    sentencing_research,
)
from .sync import (
    import_cases,
    run_sync,
    sync_cases,
    sync_status,
)
from .search import (
    get_section,
    get_section_range,
    get_statute_history,
    list_ordinances,
    list_section_versions,
    search_legislation,
    verify_citation,
    verify_citations,
)


def _dump(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hk-law",
        description="Hong Kong criminal law corpus and MCP server",
    )
    parser.add_argument("--db", help="SQLite database path (default: HK_LAW_DB)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create/update the SQLite schema")
    sub.add_parser("stats", help="Show corpus statistics")

    download = sub.add_parser("download", help="Download official e-Legislation ZIPs")
    download.add_argument("--data-dir", default="data/raw")
    download.add_argument("--languages", nargs="+", default=["en", "zh-Hant"])
    download.add_argument(
        "--dataset",
        choices=["current", "past", "both"],
        default="current",
        help="current version (default), past versions, or both",
    )
    download.add_argument(
        "--ranges",
        nargs="+",
        default=None,
        help="Dataset-specific ranges; omit to use defaults for the dataset",
    )
    download.add_argument("--force", action="store_true")

    sync_p = sub.add_parser(
        "sync", help="Update legislation and import/sync authorised judgments"
    )
    sync_p.add_argument("--data-dir", default="data/raw")
    sync_p.add_argument("--languages", nargs="+", default=["en", "zh-Hant"])
    sync_p.add_argument(
        "--dataset", choices=["current", "past", "both"], default="current"
    )
    sync_p.add_argument("--force", action="store_true")
    sync_p.add_argument(
        "--no-legislation", action="store_true", help="Skip the DATA.GOV.HK update"
    )
    sync_p.add_argument(
        "--no-cases", action="store_true", help="Skip case imports/sync"
    )
    sync_p.add_argument(
        "--no-doj", action="store_true", help="Skip the DOJ publications update"
    )
    sync_p.add_argument(
        "--doj-lang",
        choices=["en", "zh-Hant"],
        default="en",
        help="DOJ language to update (default: en)",
    )
    sync_p.add_argument(
        "--doj-base-url",
        default=None,
        help="Override the DOJ base URL (default: HK_LAW_DOJ_BASE)",
    )
    sync_p.add_argument(
        "--cases-dir",
        default=None,
        help="Authorised judgment drop folder (or set HK_LAW_CASE_IMPORT_DIR)",
    )
    sync_p.add_argument(
        "--case-format",
        choices=["auto", "jsonl", "csv", "json", "sqlite", "html"],
        default="auto",
    )
    sync_p.add_argument(
        "--citations",
        default=None,
        help="Authorised citation list for the permission-gated HKLII adapter",
    )
    sync_p.add_argument("--source", default=None)
    sync_p.add_argument("--license", default=None)

    import_p = sub.add_parser(
        "import-cases", help="Import an authorised judgment corpus into SQLite"
    )
    import_p.add_argument("--path", required=True)
    import_p.add_argument(
        "--format",
        choices=["auto", "jsonl", "csv", "json", "sqlite", "html"],
        default="auto",
    )
    import_p.add_argument("--source", default=None)
    import_p.add_argument("--license", default=None)
    import_p.add_argument("--permission-ref", default=None)

    sub.add_parser("sync-status", help="Show local coverage and sync freshness")

    sync_doj_p = sub.add_parser(
        "sync-doj", help="Update the DOJ Prosecution Code and policies"
    )
    sync_doj_p.add_argument("--force", action="store_true")
    sync_doj_p.add_argument("--lang", choices=["en", "zh-Hant"], default="en")
    sync_doj_p.add_argument("--base-url", default=None)

    search_doj_p = sub.add_parser(
        "search-doj", help="Search DOJ Prosecution Code and policies"
    )
    search_doj_p.add_argument("query")
    search_doj_p.add_argument(
        "--category",
        choices=["prosecution_code", "domestic_violence"],
        default=None,
    )
    search_doj_p.add_argument("--lang", default="en")
    search_doj_p.add_argument("--limit", type=int, default=8)
    search_doj_p.add_argument("--text", action="store_true", dest="include_text")
    search_doj_p.add_argument("--max-chars", type=int, default=4000)

    get_doj_p = sub.add_parser("get-doj", help="Read a DOJ publication")
    get_doj_p.add_argument("slug")
    get_doj_p.add_argument("--lang", default="en")
    get_doj_p.add_argument("--paragraphs", nargs="*")
    get_doj_p.add_argument("--max-chars", type=int, default=20000)

    list_doj_p = sub.add_parser("list-doj", help="List DOJ publications")
    list_doj_p.add_argument(
        "--category",
        choices=["prosecution_code", "domestic_violence"],
        default=None,
    )
    list_doj_p.add_argument("--lang", default="en")
    list_doj_p.add_argument("--limit", type=int, default=200)

    verify_doj_p = sub.add_parser(
        "verify-doj", help="Verify a DOJ policy citation"
    )
    verify_doj_p.add_argument("citation")
    verify_doj_p.add_argument(
        "--category",
        choices=["prosecution_code", "domestic_violence"],
        default=None,
    )
    verify_doj_p.add_argument("--lang", default="en")

    sub.add_parser("doj-status", help="Show DOJ coverage and freshness")

    ingest = sub.add_parser("ingest", help="Index e-Legislation ZIPs into SQLite")
    ingest.add_argument("--data-dir", default="data/raw")
    ingest.add_argument("--language", choices=["en", "zh-Hant", "zh-Hans"])
    ingest.add_argument("--zip", nargs="*", default=None)
    ingest.add_argument(
        "--dataset",
        choices=["auto", "current", "past"],
        default="auto",
        help="auto-detect from filenames (default), current-only, or past-only",
    )

    search_leg = sub.add_parser("search-legislation", help="Search legislation")
    search_leg.add_argument("query")
    search_leg.add_argument("--cap")
    search_leg.add_argument("--lang", default="en")
    search_leg.add_argument("--limit", type=int, default=8)
    search_leg.add_argument("--text", action="store_true", dest="include_text")
    search_leg.add_argument("--max-chars", type=int, default=4000)

    get_sec = sub.add_parser("get-section", help="Get one section/schedule")
    get_sec.add_argument("cap")
    get_sec.add_argument("section")
    get_sec.add_argument("--lang", default="en")
    get_sec.add_argument("--max-chars", type=int, default=20000)

    get_range = sub.add_parser("get-section-range", help="Get a range of sections")
    get_range.add_argument("cap")
    get_range.add_argument("start")
    get_range.add_argument("end")
    get_range.add_argument("--lang", default="en")
    get_range.add_argument("--max-chars", type=int, default=4000)
    get_range.add_argument("--limit", type=int, default=100)

    history = sub.add_parser("statute-history", help="Point-in-time provision text")
    history.add_argument("cap")
    history.add_argument("section")
    history.add_argument("--as-of", help="YYYY-MM-DD (default: today)")
    history.add_argument("--lang", default="en")
    history.add_argument("--max-chars", type=int, default=20000)

    versions = sub.add_parser(
        "section-versions", help="List historical versions of a section"
    )
    versions.add_argument("cap")
    versions.add_argument("section")
    versions.add_argument("--lang", default="en")

    sub.add_parser("list-ordinances", help="List indexed ordinances")

    search_cases_p = sub.add_parser("search-cases", help="Search judgments")
    search_cases_p.add_argument("query")
    search_cases_p.add_argument("--court")
    search_cases_p.add_argument("--year-from", type=int)
    search_cases_p.add_argument("--year-to", type=int)
    search_cases_p.add_argument("--limit", type=int, default=10)
    search_cases_p.add_argument("--lang", default="en")
    search_cases_p.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )
    search_cases_p.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    search_cases_p.add_argument("--no-live", action="store_true", help=argparse.SUPPRESS)

    get_case_p = sub.add_parser("get-case", help="Read or fetch a judgment")
    get_case_p.add_argument("citation")
    get_case_p.add_argument("--lang", default="en")
    get_case_p.add_argument("--paragraphs", nargs="*")
    get_case_p.add_argument("--max-chars", type=int, default=20000)
    get_case_p.add_argument(
        "--local-only", action="store_true", help="Never contact HKLII"
    )

    verify = sub.add_parser("verify", help="Verify a citation")
    verify.add_argument("citation")
    verify.add_argument("--lang", default="en")
    verify.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )
    verify.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    verify.add_argument("--no-live", action="store_true", help=argparse.SUPPRESS)

    verify_text = sub.add_parser(
        "verify-text", help="Extract and verify all citations in a passage"
    )
    verify_text.add_argument("text")
    verify_text.add_argument("--lang", default="en")
    verify_text.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )
    verify_text.add_argument("--live", action="store_true", help=argparse.SUPPRESS)

    note = sub.add_parser("note-up", help="Read cached or permitted note-up data")
    note.add_argument("citation")
    note.add_argument("--force", action="store_true")
    note.add_argument(
        "--local-only", action="store_true", help="Use only cached note-up data"
    )

    doctrine = sub.add_parser(
        "doctrine", help="Legislation + ranked case leads for an issue"
    )
    doctrine.add_argument("query")
    doctrine.add_argument("--lang", default="en")
    doctrine.add_argument("--legislation-limit", type=int, default=5)
    doctrine.add_argument("--case-limit", type=int, default=5)
    doctrine.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )

    sentencing = sub.add_parser(
        "sentencing", help="Penalty text + sentencing case leads"
    )
    sentencing.add_argument("cap")
    sentencing.add_argument("section")
    sentencing.add_argument("--lang", default="en")
    sentencing.add_argument("--case-limit", type=int, default=5)
    sentencing.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )

    authority = sub.add_parser(
        "authority", help="Rank case results by court level and cached note-up"
    )
    authority.add_argument("query")
    authority.add_argument("--court")
    authority.add_argument("--limit", type=int, default=10)
    authority.add_argument("--lang", default="en")
    authority.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )

    graph = sub.add_parser(
        "case-graph", help="Outgoing and incoming citations for a case"
    )
    graph.add_argument("citation")
    graph.add_argument("--lang", default="en")
    graph.add_argument(
        "--local-only", action="store_true", help="Do not contact HKLII"
    )
    graph.add_argument("--live", action="store_true", help=argparse.SUPPRESS)
    graph.add_argument("--no-live", action="store_true", help=argparse.SUPPRESS)

    sub.add_parser("serve", help="Run the MCP server on stdio")

    serve_http = sub.add_parser(
        "serve-http",
        help="Run the remote HTTP server (MCP, JSON API, OpenAPI, mobile web app)",
    )
    serve_http.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    serve_http.add_argument("--port", type=int, default=None, help="port (default 8765)")
    serve_http.add_argument(
        "--access-key",
        default=None,
        help="shared secret for clients (or HK_LAW_HTTP_ACCESS_KEY)",
    )
    serve_http.add_argument(
        "--public-url",
        default=None,
        help="public https:// base URL; enables OAuth for hosted assistants",
    )
    serve_http.add_argument(
        "--anonymous",
        action="store_true",
        help="allow unauthenticated access on a non-loopback bind",
    )
    serve_http.add_argument(
        "--allowed-host", action="append", default=None, help="allowed Host header"
    )
    serve_http.add_argument(
        "--allowed-origin", action="append", default=None, help="allowed Origin"
    )
    serve_http.add_argument("--rate-limit", type=int, default=None)
    serve_http.add_argument("--rate-window", type=int, default=None)
    serve_http.add_argument("--trust-proxy", action="store_true")
    serve_http.add_argument(
        "--stateful",
        action="store_true",
        help="keep MCP sessions instead of stateless HTTP",
    )
    serve_http.add_argument(
        "--json-response",
        action="store_true",
        help="return application/json instead of SSE for MCP responses",
    )
    serve_http.add_argument(
        "--allow-sync",
        action="store_true",
        help="expose sync_doj on the remote server (hidden by default)",
    )
    serve_http.add_argument("--log-level", default="info")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.db:
        os.environ["HK_LAW_DB"] = str(Path(args.db).expanduser())

    if args.command == "serve-http":
        from .http_server import main as serve_http_main

        forwarded: list[str] = ["--log-level", args.log_level]
        if args.host:
            forwarded += ["--host", args.host]
        if args.port is not None:
            forwarded += ["--port", str(args.port)]
        if args.access_key:
            forwarded += ["--access-key", args.access_key]
        if args.public_url:
            forwarded += ["--public-url", args.public_url]
        if args.anonymous:
            forwarded.append("--anonymous")
        for host in args.allowed_host or []:
            forwarded += ["--allowed-host", host]
        for origin in args.allowed_origin or []:
            forwarded += ["--allowed-origin", origin]
        if args.rate_limit is not None:
            forwarded += ["--rate-limit", str(args.rate_limit)]
        if args.rate_window is not None:
            forwarded += ["--rate-window", str(args.rate_window)]
        if args.trust_proxy:
            forwarded.append("--trust-proxy")
        if args.stateful:
            forwarded.append("--stateful")
        if args.json_response:
            forwarded.append("--json-response")
        if args.allow_sync:
            forwarded.append("--allow-sync")
        serve_http_main(forwarded)
        return

    if args.command == "init-db":
        conn = connect()
        print(f"initialised {db_path()}")
        conn.close()
        return

    if args.command == "stats":
        conn = connect()
        _dump({"status": "ok", "corpus": stats(conn)})
        conn.close()
        return

    if args.command == "download":
        paths = download_archives(
            Path(args.data_dir),
            languages=args.languages,
            ranges=args.ranges,
            force=args.force,
            progress=_progress,
            dataset=args.dataset,
        )
        _dump({"downloaded": [str(p) for p in paths]})
        return

    if args.command == "sync":
        conn = connect()
        try:
            result = run_sync(
                conn,
                data_dir=args.data_dir,
                languages=args.languages,
                dataset=args.dataset,
                force=args.force,
                include_legislation=not args.no_legislation,
                include_cases=not args.no_cases,
                include_doj=not args.no_doj,
                doj_language=args.doj_lang,
                doj_base_url=args.doj_base_url,
                cases_dir=args.cases_dir,
                case_format=args.case_format,
                citations=args.citations,
                source=args.source,
                license=args.license,
                progress=_progress,
            )
            _dump({"status": "ok", **result, "corpus": sync_status(conn)})
        finally:
            conn.close()
        return

    if args.command == "import-cases":
        conn = connect()
        try:
            result = import_cases(
                conn,
                args.path,
                format=args.format,
                source=args.source,
                license=args.license,
                permission_ref=args.permission_ref,
                progress=_progress,
            )
            _dump({"status": "ok", **result, "corpus": sync_status(conn)})
        finally:
            conn.close()
        return

    if args.command == "sync-status":
        conn = connect()
        try:
            _dump({"status": "ok", "sync": sync_status(conn)})
        finally:
            conn.close()
        return

    if args.command == "sync-doj":
        conn = connect()
        try:
            result = sync_doj(
                conn,
                force=args.force,
                language=args.lang,
                base_url=args.base_url,
                progress=_progress,
            )
            _dump({"status": "ok", **result, "corpus": doj_status(conn)})
        finally:
            conn.close()
        return

    if args.command == "doj-status":
        conn = connect()
        try:
            _dump({"status": "ok", "doj": doj_status(conn)})
        finally:
            conn.close()
        return

    if args.command == "search-doj":
        conn = connect()
        try:
            _dump(
                search_doj(
                    conn,
                    args.query,
                    category=args.category,
                    language=args.lang,
                    limit=args.limit,
                    include_text=args.include_text,
                    max_chars=args.max_chars,
                )
            )
        finally:
            conn.close()
        return

    if args.command == "get-doj":
        conn = connect()
        try:
            _dump(
                get_doj_document(
                    conn,
                    args.slug,
                    language=args.lang,
                    paragraphs=args.paragraphs,
                    max_chars=args.max_chars,
                )
            )
        finally:
            conn.close()
        return

    if args.command == "list-doj":
        conn = connect()
        try:
            _dump(
                list_doj_documents(
                    conn,
                    category=args.category,
                    language=args.lang,
                    limit=args.limit,
                )
            )
        finally:
            conn.close()
        return

    if args.command == "verify-doj":
        conn = connect()
        try:
            _dump(
                verify_doj_citation(
                    conn,
                    args.citation,
                    category=args.category,
                    language=args.lang,
                )
            )
        finally:
            conn.close()
        return

    if args.command == "ingest":
        if args.zip:
            paths = [Path(p) for p in args.zip]
        else:
            paths = sorted(Path(args.data_dir).glob("*.zip"))
        if args.dataset == "current":
            paths = [p for p in paths if not is_history_archive(p)]
        elif args.dataset == "past":
            paths = [p for p in paths if is_history_archive(p)]
        if not paths:
            parser.error("no ZIP archives found for the selected dataset")
        conn = connect()
        result = ingest_archives(
            conn, paths, only_language=args.language, progress=_progress
        )
        _dump({"status": "ok", "ingested": result, "corpus": stats(conn)})
        conn.close()
        return

    conn = connect()
    try:
        if args.command == "search-legislation":
            _dump(
                search_legislation(
                    conn,
                    args.query,
                    cap=args.cap,
                    lang=args.lang,
                    limit=args.limit,
                    include_text=args.include_text,
                    max_chars=args.max_chars,
                )
            )
        elif args.command == "get-section":
            _dump(
                get_section(
                    conn,
                    args.cap,
                    args.section,
                    lang=args.lang,
                    max_chars=args.max_chars,
                )
            )
        elif args.command == "get-section-range":
            _dump(
                get_section_range(
                    conn,
                    args.cap,
                    args.start,
                    args.end,
                    lang=args.lang,
                    max_chars=args.max_chars,
                    limit=args.limit,
                )
            )
        elif args.command == "statute-history":
            _dump(
                get_statute_history(
                    conn,
                    args.cap,
                    args.section,
                    as_of=args.as_of,
                    lang=args.lang,
                    max_chars=args.max_chars,
                )
            )
        elif args.command == "section-versions":
            _dump(list_section_versions(conn, args.cap, args.section, args.lang))
        elif args.command == "list-ordinances":
            _dump(list_ordinances(conn))
        elif args.command == "search-cases":
            _dump(
                search_cases(
                    conn,
                    args.query,
                    court=args.court,
                    year_from=args.year_from,
                    year_to=args.year_to,
                    limit=args.limit,
                    lang=args.lang,
                    live=not args.local_only and not args.no_live,
                )
            )
        elif args.command == "get-case":
            allow_live = not args.local_only
            if args.paragraphs:
                _dump(
                    get_case_paragraphs(
                        conn,
                        args.citation,
                        args.paragraphs,
                        args.lang,
                        allow_live=allow_live,
                    )
                )
            else:
                result = get_judgment(
                    conn, args.citation, lang=args.lang, allow_live=allow_live
                )
                text = result.get("text") or ""
                if len(text) > args.max_chars:
                    result["text"] = text[: args.max_chars]
                    result["truncated"] = True
                    result["full_text_chars"] = len(text)
                _dump(result)
        elif args.command == "verify":
            _dump(
                verify_citation(
                    conn,
                    args.citation,
                    lang=args.lang,
                    live=not args.local_only and not args.no_live,
                )
            )
        elif args.command == "verify-text":
            _dump(
                verify_citations(
                    conn, args.text, lang=args.lang, live=not args.local_only
                )
            )
        elif args.command == "doctrine":
            _dump(
                doctrine_research(
                    conn,
                    args.query,
                    lang=args.lang,
                    legislation_limit=args.legislation_limit,
                    case_limit=args.case_limit,
                    live_cases=not args.local_only,
                )
            )
        elif args.command == "sentencing":
            _dump(
                sentencing_research(
                    conn,
                    args.cap,
                    args.section,
                    lang=args.lang,
                    case_limit=args.case_limit,
                    live_cases=not args.local_only,
                )
            )
        elif args.command == "authority":
            _dump(
                authority_ranking(
                    conn,
                    args.query,
                    court=args.court,
                    limit=args.limit,
                    lang=args.lang,
                    live=not args.local_only,
                )
            )
        elif args.command == "case-graph":
            _dump(
                case_graph(
                    conn,
                    args.citation,
                    lang=args.lang,
                    live_note_up=not args.local_only and not args.no_live,
                )
            )
        elif args.command == "note-up":
            _dump(
                note_up(
                    conn,
                    args.citation,
                    force=args.force,
                    allow_live=not args.local_only,
                )
            )
        elif args.command == "serve":
            from .server import mcp

            mcp.run()
        else:
            parser.error(f"unknown command {args.command}")
    finally:
        if args.command != "serve":
            conn.close()


if __name__ == "__main__":
    main()
