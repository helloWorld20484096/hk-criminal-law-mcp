"""Local corpus sync, incremental legislation updates, and judgment import.

Design rules
------------
* Legislation is updated from the official DATA.GOV.HK e-Legislation archives.
* Judgments are imported from a corpus the operator is authorised to use, or
  fetched through an explicitly permission-gated adapter. There is no default
  LRS/HKLII crawler: the Judiciary's LRS disallows crawling and HKLII's terms
  prohibit automated harvesting. ``sync_cases`` refuses to run without a
  permission reference and an explicit citation list.
* Every run is recorded in ``sync_runs`` and every imported source in
  ``case_sources`` so the MCP can report what is local and how fresh it is.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

import httpx

from .citations import COURT_NAMES, parse_case_citation
from .config import (
    DATA_GOV_BASE,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
    case_citations_file,
    case_import_dir,
    case_permission_ref,
    case_source_name,
    case_source_url,
    local_only,
)
from .db import stats
from .doj import doj_status, sync_doj
from .hklii import _parse_judgment_html, get_judgment, store_case
from .ingest_legislation import (
    CURRENT_ARCHIVES,
    CURRENT_RANGES,
    PAST_ARCHIVES,
    PAST_RANGES,
    archive_url,
    ingest_archives,
)


class SyncError(RuntimeError):
    pass


class PermissionRequiredError(SyncError):
    """Raised before any automated case access without written permission."""


# ---------------------------------------------------------------------------
# Sync-run and meta helpers
# ---------------------------------------------------------------------------


def _meta_get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _meta_set(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def _start_run(conn: sqlite3.Connection, kind: str, source: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO sync_runs(kind, source) VALUES (?,?)", (kind, source)
    )
    conn.commit()
    return int(cur.lastrowid)


def _finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    stats_payload: dict,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE sync_runs SET finished_at=datetime('now'), status=?, "
        "stats_json=?, error=? WHERE id=?",
        (status, json.dumps(stats_payload, ensure_ascii=False), error, run_id),
    )
    conn.commit()


def _archive_key(filename: str, suffix: str) -> str:
    return f"archive.{filename}.{suffix}"


def _archive_ingested(conn: sqlite3.Connection, filename: str) -> bool:
    """Return True when the local DB already has documents from this archive."""
    table = (
        "legislation_history_docs"
        if filename.startswith("hkel_p_")
        else "legislation_docs"
    )
    row = conn.execute(
        f"SELECT 1 FROM {table} WHERE source_file LIKE ? LIMIT 1",
        (f"{filename}:%",),
    ).fetchone()
    return bool(row)


def _store_archive_headers(
    conn: sqlite3.Connection, filename: str, headers: httpx.Headers
) -> None:
    for suffix in ("etag", "last-modified", "content-length"):
        value = headers.get(suffix)
        if value:
            _meta_set(conn, _archive_key(filename, suffix), value)
    _meta_set(conn, _archive_key(filename, "checked_at"), time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    conn.commit()


def _stream_to_file(response: httpx.Response, target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    with open(tmp, "wb") as fh:
        for chunk in response.iter_bytes(1024 * 1024):
            fh.write(chunk)
    tmp.replace(target)


def _download_if_changed(
    client: httpx.Client,
    url: str,
    target: Path,
    conn: sqlite3.Connection,
    force: bool,
    progress: Callable[[str], None] | None,
) -> bool:
    """Download ``url`` to ``target`` only when the remote archive changed.

    Uses ETag/Last-Modified when the server supplies them, then falls back to a
    size comparison. Returns True when a download happened.
    """
    if target.exists() and not force:
        etag = _meta_get(conn, _archive_key(target.name, "etag"))
        modified = _meta_get(conn, _archive_key(target.name, "last-modified"))
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if modified:
            headers["If-Modified-Since"] = modified
        if headers:
            with client.stream("GET", url, headers=headers) as response:
                if response.status_code == 304:
                    return False
                response.raise_for_status()
                _stream_to_file(response, target)
                _store_archive_headers(conn, target.name, response.headers)
                return True
        # No validators: one cheap HEAD, then compare size.
        try:
            head = client.head(url)
            if head.status_code < 400:
                remote_size = head.headers.get("content-length")
                if remote_size and int(remote_size) == target.stat().st_size:
                    return False
        except (httpx.HTTPError, ValueError):
            pass

    if progress:
        progress(f"downloading {target.name}")
    with client.stream("GET", url) as response:
        response.raise_for_status()
        _stream_to_file(response, target)
        _store_archive_headers(conn, target.name, response.headers)
    return True


# ---------------------------------------------------------------------------
# Legislation
# ---------------------------------------------------------------------------


def sync_legislation(
    conn: sqlite3.Connection,
    data_dir: str | Path = "data/raw",
    languages: Iterable[str] = ("en", "zh-Hant"),
    dataset: str = "current",
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Check DATA.GOV.HK, download changed archives, and ingest only changes."""
    if dataset not in {"current", "past", "both"}:
        raise SyncError("dataset must be current, past, or both")
    dest = Path(data_dir).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    run_id = _start_run(conn, f"legislation_{dataset}", "data.gov.hk")
    totals = {
        "archives_checked": 0,
        "archives_downloaded": 0,
        "archives_unchanged": 0,
        "documents": 0,
        "sections": 0,
        "skipped": 0,
        "failed": 0,
    }
    try:
        selected: list[tuple[str, dict[tuple[str, str], str], tuple[str, ...]]] = []
        if dataset in {"current", "both"}:
            selected.append(("current", CURRENT_ARCHIVES, CURRENT_RANGES))
        if dataset in {"past", "both"}:
            selected.append(("past", PAST_ARCHIVES, PAST_RANGES))

        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for _name, mapping, ranges in selected:
                for language in languages:
                    for rng in ranges:
                        filename = mapping.get((rng, language))
                        if not filename:
                            continue
                        totals["archives_checked"] += 1
                        target = dest / filename
                        if progress:
                            progress(f"checking {filename}")
                        changed = _download_if_changed(
                            client, archive_url(filename), target, conn, force, progress
                        )
                        if (
                            not changed
                            and target.exists()
                            and _archive_ingested(conn, filename)
                        ):
                            totals["archives_unchanged"] += 1
                            continue
                        totals["archives_downloaded"] += 1
                        counts = ingest_archives(
                            conn,
                            [target],
                            only_language=language,
                            progress=progress,
                            skip_unchanged=not force,
                        )
                        for key in ("documents", "sections", "skipped", "failed"):
                            totals[key] += counts.get(key, 0)

        status = "ok" if totals["failed"] == 0 else "partial"
        _meta_set(conn, f"legislation_{dataset}.last_sync", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        conn.commit()
        _finish_run(conn, run_id, status, totals)
        return {"status": status, "kind": f"legislation_{dataset}", "stats": totals}
    except Exception as exc:
        _finish_run(conn, run_id, "failed", totals, str(exc))
        raise


# ---------------------------------------------------------------------------
# Judgment import
# ---------------------------------------------------------------------------


def _read_citations(path: str | Path | None) -> list[str]:
    if not path:
        return []
    p = Path(path).expanduser()
    if not p.exists():
        raise SyncError(f"citation list not found: {p}")
    citations = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            citations.append(line)
    return citations


def _citation_from_filename(stem: str) -> str | None:
    match = re.search(r"\[?(\d{4})\]?[\s_-]*([A-Za-z]+)[\s_-]*(\d+)", stem)
    if not match:
        return None
    return f"[{match.group(1)}] {match.group(2).upper()} {match.group(3)}"


def _split_paragraphs(text: str) -> list[dict]:
    """Turn plain text into numbered paragraphs without inventing content."""
    text = (text or "").strip()
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numbered: list[dict] = []
    current: dict | None = None
    for line in lines:
        match = re.match(r"^(\d+)[.)]?\s+(.*)$", line)
        if match:
            if current:
                numbered.append(current)
            current = {"number": match.group(1), "text": match.group(2).strip()}
        elif current:
            current["text"] = f"{current['text']} {line}".strip()
    if current:
        numbered.append(current)
    if numbered:
        return numbered
    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    return [{"number": str(i), "text": block} for i, block in enumerate(blocks, start=1)]


def _normalise_paragraphs(raw: Any) -> list[dict]:
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return _split_paragraphs(raw)
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            number = str(item.get("number") or item.get("para_no") or index)
            text = str(item.get("text") or "")
        else:
            number = str(index)
            text = str(item)
        if text.strip():
            out.append({"number": number, "text": text.strip()})
    return out


def _normalise_case_record(record: dict) -> tuple:
    citation = str(record.get("citation") or record.get("neutral_citation") or "").strip()
    parsed = parse_case_citation(citation)
    if parsed is None:
        court_code = str(record.get("court_code") or record.get("court") or "").upper()
        year = record.get("year")
        number = record.get("num") or record.get("number")
        if court_code and year and number:
            citation = f"[{year}] {court_code} {number}"
            parsed = parse_case_citation(citation)
    if parsed is None or not parsed.court_abbr:
        raise SyncError(f"unrecognised or missing neutral citation: {citation!r}")

    language = "zh-Hant" if str(record.get("language", "en")).lower().startswith("zh") else "en"
    court_code = str(record.get("court_code") or parsed.court_abbr).strip().lower()
    court = str(
        record.get("court") or COURT_NAMES.get(court_code, court_code.upper())
    ).strip()
    year = int(record.get("year") or parsed.year)
    number = str(record.get("num") or record.get("number") or parsed.number).strip()
    title = str(record.get("title") or citation).strip()
    judgment_date = record.get("judgment_date") or record.get("date")
    if isinstance(judgment_date, str):
        judgment_date = judgment_date.strip()
    source_url = record.get("source_url") or record.get("url")
    if isinstance(source_url, str):
        source_url = source_url.strip()
    html = str(record.get("html") or "")
    text = str(record.get("text") or "")

    paragraphs = _normalise_paragraphs(record.get("paragraphs"))
    if html and not paragraphs:
        parsed_html = _parse_judgment_html(html)
        paragraphs = parsed_html["paragraphs"]
        text = text or parsed_html["text"]
        title = record.get("title") or parsed_html["title"] or citation
    if not paragraphs and text:
        paragraphs = _split_paragraphs(text)
    if not text and paragraphs:
        text = "\n\n".join(f"{p['number']}. {p['text']}" for p in paragraphs)

    cited = record.get("cited_cases") or record.get("cases") or []
    if isinstance(cited, str):
        try:
            cited = json.loads(cited)
        except json.JSONDecodeError:
            cited = []
    parallel = record.get("parallel_citation")
    checksum = hashlib.sha256(
        (html or text or citation).encode("utf-8", errors="ignore")
    ).hexdigest()
    meta = {
        "db": court,
        "date": judgment_date,
        "doc": source_url,
        "cases": cited,
        "parallel_citation": parallel,
        "is_translation": bool(record.get("is_translation")),
        "has_translation": bool(record.get("has_translation")),
    }
    parsed_record = {"title": title, "paragraphs": paragraphs, "text": text}
    return (
        parsed.normalised,
        meta,
        parsed_record,
        language,
        court_code,
        year,
        number,
        html,
        checksum,
    )


def _iter_jsonl(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SyncError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if isinstance(item, dict):
                yield item
            else:
                raise SyncError(f"{path}:{line_no}: expected a JSON object")


def _iter_csv(path: Path) -> Iterator[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def _iter_json(path: Path) -> Iterator[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("cases", [payload])
    if not isinstance(payload, list):
        raise SyncError(f"{path}: expected a list of cases or {{'cases': [...]}}")
    for item in payload:
        if isinstance(item, dict):
            yield item
        else:
            raise SyncError(f"{path}: expected case objects")


def _iter_sqlite(path: Path) -> Iterator[dict]:
    source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "cases" not in tables:
            raise SyncError(f"{path}: no 'cases' table")
        has_paras = "case_paragraphs" in tables
        for row in source.execute("SELECT * FROM cases").fetchall():
            record = dict(row)
            if has_paras:
                record["paragraphs"] = [
                    {"number": p["para_no"], "text": p["text"]}
                    for p in source.execute(
                        "SELECT para_no, text FROM case_paragraphs WHERE case_id=?",
                        (row["id"],),
                    ).fetchall()
                ]
            yield record
    finally:
        source.close()


def _iter_html(path: Path) -> Iterator[dict]:
    html_files = sorted(path.glob("*.html")) + sorted(path.glob("*.htm"))
    for html_file in html_files:
        sidecar = html_file.with_suffix(".json")
        meta: dict = {}
        if sidecar.exists():
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                meta = payload
        citation = meta.get("citation") or _citation_from_filename(html_file.stem)
        if not citation:
            raise SyncError(
                f"{html_file}: cannot derive a neutral citation; add a .json sidecar"
            )
        meta.setdefault("citation", citation)
        meta["html"] = html_file.read_text(encoding="utf-8", errors="ignore")
        yield meta


def _iter_records(path: Path, fmt: str = "auto") -> Iterator[dict]:
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.is_file())
        if not files:
            return
        for file in files:
            if file.suffix == ".json" and file.with_suffix(".html").exists():
                continue  # sidecar consumed by the HTML reader
            yield from _iter_records(file, "auto" if fmt == "auto" else fmt)
        return
    suffix = path.suffix.lower()
    if fmt == "auto":
        if suffix in {".jsonl", ".ndjson"}:
            fmt = "jsonl"
        elif suffix == ".csv":
            fmt = "csv"
        elif suffix in {".db", ".sqlite", ".sqlite3"}:
            fmt = "sqlite"
        elif suffix in {".html", ".htm"}:
            fmt = "html"
        elif suffix == ".json":
            fmt = "json"
        else:
            raise SyncError(f"{path}: unsupported format {suffix!r}")
    if fmt == "jsonl":
        yield from _iter_jsonl(path)
    elif fmt == "csv":
        yield from _iter_csv(path)
    elif fmt == "json":
        yield from _iter_json(path)
    elif fmt == "sqlite":
        yield from _iter_sqlite(path)
    elif fmt == "html":
        yield from _iter_html(path)
    else:
        raise SyncError(f"unknown import format: {fmt}")


def _upsert_case_source(
    conn: sqlite3.Connection,
    source: str,
    license_text: str | None,
    permission_ref: str | None,
    base_url: str | None,
    count: int,
) -> None:
    conn.execute(
        """
        INSERT INTO case_sources
            (source, license, permission_ref, base_url, imported_at, last_sync_at, case_count)
        VALUES (?,?,?,?,datetime('now'),datetime('now'),?)
        ON CONFLICT(source) DO UPDATE SET
            license=COALESCE(excluded.license, case_sources.license),
            permission_ref=COALESCE(excluded.permission_ref, case_sources.permission_ref),
            base_url=COALESCE(excluded.base_url, case_sources.base_url),
            imported_at=excluded.imported_at,
            last_sync_at=excluded.last_sync_at,
            case_count=excluded.case_count
        """,
        (source, license_text, permission_ref, base_url, count),
    )
    conn.commit()


def import_cases(
    conn: sqlite3.Connection,
    path: str | Path,
    format: str = "auto",
    source: str | None = None,
    license: str | None = None,
    permission_ref: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Import a judgment corpus the operator is authorised to use.

    Supported formats: JSONL/NDJSON, CSV, a SQLite database with a ``cases``
    table, or a directory of HTML judgments with optional ``.json`` sidecars.
    Re-importing the same citation updates it in place.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise SyncError(f"import path not found: {target}")
    source = source or case_source_name()
    run_id = _start_run(conn, "cases_import", source)
    counts = {"records": 0, "imported": 0, "failed": 0}
    try:
        for record in _iter_records(target, format):
            counts["records"] += 1
            citation_hint = record.get("citation") or record.get("neutral_citation") or "?"
            try:
                case = _normalise_case_record(record)
                store_case(
                    conn,
                    *case,
                    source_url=case[1].get("doc"),
                    commit=False,
                )
                counts["imported"] += 1
                if counts["imported"] % 100 == 0:
                    conn.commit()
            except Exception as exc:
                counts["failed"] += 1
                if progress:
                    progress(f"skipped {citation_hint}: {exc}")
        conn.commit()
        _upsert_case_source(
            conn, source, license, permission_ref or case_permission_ref(), None, counts["imported"]
        )
        status = "ok" if counts["failed"] == 0 else "partial"
        _finish_run(conn, run_id, status, counts)
        return {"status": status, "source": source, "stats": counts}
    except Exception as exc:
        conn.commit()
        _finish_run(conn, run_id, "failed", counts, str(exc))
        raise


# ---------------------------------------------------------------------------
# Permission-gated judgment sync
# ---------------------------------------------------------------------------


def sync_cases(
    conn: sqlite3.Connection,
    citations: str | Path | Iterable[str] | None = None,
    source: str | None = None,
    permission_ref: str | None = None,
    limit: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Fetch an explicit, authorised citation list.

    This is not a crawler. It requires a written-permission reference and a
    citation list (``HK_LAW_CASE_CITATIONS`` or the ``citations`` argument).
    The default adapter is HKLII; a Judiciary LRS adapter needs the permitted
    URL pattern from the permission letter before it can be wired.
    """
    source = source or case_source_name()
    permission_ref = permission_ref or case_permission_ref()
    if not permission_ref:
        raise PermissionRequiredError(
            "Refusing automated case access: no permission reference. "
            "Set HK_LAW_CASE_PERMISSION_REF only after obtaining written permission "
            "from the Judiciary or HKLII. This build does not crawl LRS or HKLII."
        )
    if citations is None:
        citations = _read_citations(case_citations_file())
    elif isinstance(citations, (str, Path)):
        citations = _read_citations(citations)
    else:
        citations = [str(item).strip() for item in citations if str(item).strip()]
    if not citations:
        raise PermissionRequiredError(
            "No authorized citation list configured. Set HK_LAW_CASE_CITATIONS or "
            "pass --citations. Automatic discovery requires an authorized feed."
        )
    if limit:
        citations = citations[:limit]

    if source.lower() not in {"hklii", "hklii-authorized"}:
        raise SyncError(
            f"No adapter is wired for source {source!r}. The HKLII adapter is the "
            "only permission-gated HTTP adapter in this build; the LRS adapter "
            "needs the permitted URL pattern from the permission letter."
        )

    run_id = _start_run(conn, "cases_sync", source)
    counts = {"requested": 0, "fetched": 0, "refreshed": 0, "failed": 0}
    try:
        for citation in citations:
            counts["requested"] += 1
            parsed = parse_case_citation(citation)
            if parsed is None:
                counts["failed"] += 1
                if progress:
                    progress(f"invalid citation: {citation}")
                continue
            existed = conn.execute(
                "SELECT 1 FROM cases WHERE neutral_citation=?", (parsed.normalised,)
            ).fetchone()
            try:
                get_judgment(conn, parsed.normalised, allow_live=True)
                if existed:
                    counts["refreshed"] += 1
                else:
                    counts["fetched"] += 1
            except Exception as exc:
                counts["failed"] += 1
                if progress:
                    progress(f"failed {parsed.normalised}: {exc}")
        _upsert_case_source(
            conn,
            source,
            os.environ.get("HK_LAW_CASE_LICENSE"),
            permission_ref,
            case_source_url(),
            counts["fetched"],
        )
        status = "ok" if counts["failed"] == 0 else "partial"
        _finish_run(conn, run_id, status, counts)
        return {"status": status, "source": source, "stats": counts}
    except Exception as exc:
        _finish_run(conn, run_id, "failed", counts, str(exc))
        raise


# ---------------------------------------------------------------------------
# Orchestration and status
# ---------------------------------------------------------------------------


def run_sync(
    conn: sqlite3.Connection,
    data_dir: str | Path = "data/raw",
    languages: Iterable[str] = ("en", "zh-Hant"),
    dataset: str = "current",
    force: bool = False,
    include_legislation: bool = True,
    include_cases: bool = True,
    include_doj: bool = True,
    doj_language: str = "en",
    doj_base_url: str | None = None,
    cases_dir: str | Path | None = None,
    case_format: str = "auto",
    citations: str | Path | Iterable[str] | None = None,
    source: str | None = None,
    license: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    result: dict[str, Any] = {
        "status": "ok",
        "legislation": None,
        "cases_import": None,
        "cases_sync": None,
        "doj": None,
    }
    if include_legislation:
        result["legislation"] = sync_legislation(
            conn,
            data_dir=data_dir,
            languages=languages,
            dataset=dataset,
            force=force,
            progress=progress,
        )

    if include_cases:
        import_dir = Path(cases_dir).expanduser() if cases_dir else case_import_dir()
        if import_dir:
            result["cases_import"] = import_cases(
                conn,
                import_dir,
                format=case_format,
                source=source,
                license=license or os.environ.get("HK_LAW_CASE_LICENSE"),
                progress=progress,
            )

        if citations is not None or case_citations_file():
            try:
                result["cases_sync"] = sync_cases(
                    conn,
                    citations=citations,
                    source=source,
                    progress=progress,
                )
            except PermissionRequiredError as exc:
                result["cases_sync"] = {"status": "blocked", "reason": str(exc)}

    if include_doj:
        try:
            result["doj"] = sync_doj(
                conn,
                language=doj_language,
                base_url=doj_base_url,
                progress=progress,
            )
        except Exception as exc:
            result["doj"] = {"status": "failed", "error": str(exc)}
    return result


def _coverage(conn: sqlite3.Connection) -> dict:
    """Summarise what is local, what is missing, and how stale it is."""

    def by_language(table: str) -> dict[str, int]:
        return {
            row["language"]: row["n"]
            for row in conn.execute(
                f"SELECT language, COUNT(*) AS n FROM {table} GROUP BY language"
            ).fetchall()
        }

    current_docs = by_language("legislation_docs")
    current_sections = by_language("legislation_sections")
    history_docs = by_language("legislation_history_docs")
    history_sections = by_language("legislation_history_sections")
    cases_row = conn.execute(
        "SELECT COUNT(*) AS cases, COUNT(*) FILTER (WHERE language='en') AS en, "
        "COUNT(*) FILTER (WHERE language LIKE 'zh%') AS zh FROM cases"
    ).fetchone()
    paragraphs = conn.execute("SELECT COUNT(*) FROM case_paragraphs").fetchone()[0]
    cases_by_court = {
        row["court_code"]: row["n"]
        for row in conn.execute(
            "SELECT court_code, COUNT(*) AS n FROM cases "
            "WHERE court_code IS NOT NULL GROUP BY court_code ORDER BY n DESC"
        ).fetchall()
    }
    max_current = conn.execute(
        "SELECT MAX(version_date) FROM legislation_docs"
    ).fetchone()[0]
    hist_min, hist_max = conn.execute(
        "SELECT MIN(version_date), MAX(version_date) FROM legislation_history_docs"
    ).fetchone()
    age_row = conn.execute(
        "SELECT (julianday('now') - julianday(MAX(finished_at))) AS days "
        "FROM sync_runs WHERE status IN ('ok','partial')"
    ).fetchone()
    age_days = age_row["days"] if age_row else None

    gaps: list[str] = []
    if not current_docs:
        gaps.append(
            "Current legislation corpus is empty. Run: hk-law sync --dataset current"
        )
    elif not current_docs.get("en") or not current_docs.get("zh-Hant"):
        gaps.append(
            "Current legislation is missing English or Traditional Chinese documents."
        )
    if not history_sections:
        gaps.append(
            "Historical legislation is not ingested. Run: hk-law sync --dataset past"
        )
    elif not history_sections.get("zh-Hant"):
        gaps.append(
            "Traditional Chinese historical versions are not ingested. Run: "
            "hk-law sync --dataset past --languages zh-Hant --no-cases"
        )
    if (cases_row["cases"] if cases_row else 0) < 1000:
        gaps.append(
            "The local judgment corpus is not comprehensive. Import an authorised "
            "corpus, or set HK_LAW_LOCAL_ONLY=0 for permitted live HKLII access."
        )
    doj_count = conn.execute("SELECT COUNT(*) FROM doj_docs").fetchone()[0]
    if not doj_count:
        gaps.append(
            "DOJ Prosecution Code and prosecution policies are not indexed. "
            "Run: hk-law sync-doj"
        )
    if age_days is not None and age_days > 7:
        gaps.append(
            f"Last successful sync was {int(age_days)} days ago. Run: hk-law sync"
        )

    return {
        "legislation_current": {
            "documents": current_docs,
            "sections": current_sections,
            "latest_version_date": max_current,
        },
        "legislation_history": {
            "documents": history_docs,
            "sections": history_sections,
            "date_range": f"{hist_min} .. {hist_max}" if hist_min else None,
        },
        "judgments": {
            "cases": cases_row["cases"] if cases_row else 0,
            "english_cases": cases_row["en"] if cases_row else 0,
            "chinese_cases": cases_row["zh"] if cases_row else 0,
            "paragraphs": paragraphs,
            "by_court": cases_by_court,
        },
        "last_sync_age_days": age_days,
        "gaps": gaps,
    }


def sync_status(conn: sqlite3.Connection) -> dict:
    """Return local coverage, what is missing, sync state, and permission config."""
    payload = stats(conn)
    payload.update(
        {
            "coverage": _coverage(conn),
            "local_only": local_only(),
            "permission_configured": bool(case_permission_ref()),
            "case_source": case_source_name(),
            "case_source_url": case_source_url(),
            "case_import_dir": str(case_import_dir()) if case_import_dir() else None,
            "case_citations_file": str(case_citations_file()) if case_citations_file() else None,
            "doj": doj_status(conn),
            "case_source_rows": [
                dict(row)
                for row in conn.execute(
                    "SELECT source, license, permission_ref, base_url, imported_at, "
                    "last_sync_at, case_count FROM case_sources ORDER BY source"
                ).fetchall()
            ],
            "recent_syncs": [
                dict(row)
                for row in conn.execute(
                    "SELECT id, kind, source, started_at, finished_at, status, error "
                    "FROM sync_runs ORDER BY id DESC LIMIT 10"
                ).fetchall()
            ],
        }
    )
    return payload
