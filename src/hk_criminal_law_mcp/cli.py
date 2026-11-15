"""Command-line interface for the HK criminal law corpus and MCP server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import db_path, DISCLAIMER
from .db import connect, stats
from .hklii import get_case_paragraphs, get_judgment, note_up, search_cases
from .ingest_legislation import download_archives, ingest_archives
from .search import get_section, list_ordinances, search_legislation, verify_citation


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
        "--ranges", nargs="+", default=["1-300", "301-600", "601+", "instruments"]
    )
    download.add_argument("--force", action="store_true")

    ingest = sub.add_parser("ingest", help="Index e-Legislation ZIPs into SQLite")
    ingest.add_argument("--data-dir", default="data/raw")
    ingest.add_argument("--language", choices=["en", "zh-Hant", "zh-Hans"])
    ingest.add_argument("--zip", nargs="*", default=None)

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

    sub.add_parser("list-ordinances", help="List indexed ordinances")

    search_cases_p = sub.add_parser("search-cases", help="Search judgments")
    search_cases_p.add_argument("query")
    search_cases_p.add_argument("--court")
    search_cases_p.add_argument("--year-from", type=int)
    search_cases_p.add_argument("--year-to", type=int)
    search_cases_p.add_argument("--limit", type=int, default=10)
    search_cases_p.add_argument("--lang", default="en")
    search_cases_p.add_argument("--no-live", action="store_true")

    get_case_p = sub.add_parser("get-case", help="Fetch/cache a judgment")
    get_case_p.add_argument("citation")
    get_case_p.add_argument("--lang", default="en")
    get_case_p.add_argument("--paragraphs", nargs="*")
    get_case_p.add_argument("--max-chars", type=int, default=20000)

    verify = sub.add_parser("verify", help="Verify a citation")
    verify.add_argument("citation")
    verify.add_argument("--lang", default="en")
    verify.add_argument("--no-live", action="store_true")

    note = sub.add_parser("note-up", help="Fetch HKLII note-up data")
    note.add_argument("citation")
    note.add_argument("--force", action="store_true")

    sub.add_parser("serve", help="Run the MCP server on stdio")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.db:
        os.environ["HK_LAW_DB"] = str(Path(args.db).expanduser())

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
        )
        _dump({"downloaded": [str(p) for p in paths]})
        return

    if args.command == "ingest":
        if args.zip:
            paths = [Path(p) for p in args.zip]
        else:
            paths = sorted(Path(args.data_dir).glob("*.zip"))
        if not paths:
            parser.error("no ZIP archives found")
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
                    live=not args.no_live,
                )
            )
        elif args.command == "get-case":
            if args.paragraphs:
                _dump(get_case_paragraphs(conn, args.citation, args.paragraphs, args.lang))
            else:
                result = get_judgment(conn, args.citation, lang=args.lang)
                text = result.get("text") or ""
                if len(text) > args.max_chars:
                    result["text"] = text[: args.max_chars]
                    result["truncated"] = True
                    result["full_text_chars"] = len(text)
                _dump(result)
        elif args.command == "verify":
            _dump(verify_citation(conn, args.citation, lang=args.lang, live=not args.no_live))
        elif args.command == "note-up":
            _dump(note_up(conn, args.citation, force=args.force))
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
