"""Download and index Hong Kong e-Legislation bulk XML."""

from __future__ import annotations

import hashlib
import sqlite3
import zipfile
from pathlib import Path
from typing import Callable, Iterable

import httpx

from .config import DATA_GOV_BASE, ELEGISLATION_BASE, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from .legislation_xml import ParsedDocument, parse_document

CURRENT_ARCHIVES: dict[tuple[str, str], str] = {
    ("1-300", "en"): "hkel_c_leg_cap_1_cap_300_en.zip",
    ("301-600", "en"): "hkel_c_leg_cap_301_cap_600_en.zip",
    ("601+", "en"): "hkel_c_leg_cap_601_cap_end_en.zip",
    ("instruments", "en"): "hkel_c_instruments_en.zip",
    ("1-300", "zh-Hant"): "hkel_c_leg_cap_1_cap_300_zh-Hant.zip",
    ("301-600", "zh-Hant"): "hkel_c_leg_cap_301_cap_600_zh-Hant.zip",
    ("601+", "zh-Hant"): "hkel_c_leg_cap_601_cap_end_zh-Hant.zip",
    ("instruments", "zh-Hant"): "hkel_c_instruments_zh-Hant.zip",
}

PAST_ARCHIVES: dict[tuple[str, str], str] = {
    ("1-200", "en"): "hkel_p_leg_cap_1_cap_200_en.zip",
    ("201-400", "en"): "hkel_p_leg_cap_201_cap_400_en.zip",
    ("401-600", "en"): "hkel_p_leg_cap_401_cap_600_en.zip",
    ("601+", "en"): "hkel_p_leg_cap_601_cap_end_en.zip",
    ("instruments", "en"): "hkel_p_instruments_en.zip",
    ("1-200", "zh-Hant"): "hkel_p_leg_cap_1_cap_200_zh-Hant.zip",
    ("201-400", "zh-Hant"): "hkel_p_leg_cap_201_cap_400_zh-Hant.zip",
    ("401-600", "zh-Hant"): "hkel_p_leg_cap_401_cap_600_zh-Hant.zip",
    ("601+", "zh-Hant"): "hkel_p_leg_cap_601_cap_end_zh-Hant.zip",
    ("instruments", "zh-Hant"): "hkel_p_instruments_zh-Hant.zip",
}

CURRENT_RANGES = ("1-300", "301-600", "601+", "instruments")
PAST_RANGES = ("1-200", "201-400", "401-600", "601+", "instruments")


def archive_url(filename: str) -> str:
    return f"{DATA_GOV_BASE}/{filename}"


def is_history_archive(path: Path) -> bool:
    """Return True for the DATA.GOV.HK past-version archives."""
    return path.name.startswith("hkel_p_") or "_p_" in path.stem


def download_archives(
    dest: Path,
    languages: Iterable[str] = ("en", "zh-Hant"),
    ranges: Iterable[str] | None = None,
    force: bool = False,
    progress: Callable[[str], None] | None = None,
    dataset: str = "current",
) -> list[Path]:
    """Download official HKeL ZIP archives.

    ``dataset`` is ``current`` (default), ``past`` (point-in-time versions), or
    ``both``. Files come from DATA.GOV.HK (Hong Kong Department of Justice).
    Reuse is subject to the DATA.GOV.HK terms of use; attribution is required.
    """
    if dataset == "both":
        return download_archives(
            dest, languages, None, force, progress, dataset="current"
        ) + download_archives(
            dest, languages, None, force, progress, dataset="past"
        )
    if dataset not in {"current", "past"}:
        raise ValueError("dataset must be current, past, or both")
    mapping = CURRENT_ARCHIVES if dataset == "current" else PAST_ARCHIVES
    if ranges is None:
        ranges = CURRENT_RANGES if dataset == "current" else PAST_RANGES

    dest.mkdir(parents=True, exist_ok=True)
    wanted = [(r, lang) for lang in languages for r in ranges]
    out: list[Path] = []
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for rng, lang in wanted:
            filename = mapping.get((rng, lang))
            if not filename:
                continue
            target = dest / filename
            if target.exists() and target.stat().st_size > 0 and not force:
                if progress:
                    progress(f"cached {target.name} ({target.stat().st_size / 1e6:.0f} MB)")
                out.append(target)
                continue
            tmp = target.with_suffix(".part")
            if progress:
                progress(f"downloading {filename}")
            with client.stream("GET", archive_url(filename)) as response:
                response.raise_for_status()
                with open(tmp, "wb") as fh:
                    for chunk in response.iter_bytes(1024 * 1024):
                        fh.write(chunk)
            tmp.replace(target)
            if progress:
                progress(f"saved {target.name} ({target.stat().st_size / 1e6:.0f} MB)")
            out.append(target)
    return out


def _source_url(doc: ParsedDocument) -> str:
    lang = "en" if doc.language == "en" else "zh-Hant"
    return f"{ELEGISLATION_BASE}/hk/{doc.cap}!{lang}"


def _delete_document_sections(conn: sqlite3.Connection, doc_id: int) -> None:
    conn.execute(
        "DELETE FROM legislation_fts_en WHERE rowid IN "
        "(SELECT id FROM legislation_sections WHERE doc_id=?)",
        (doc_id,),
    )
    conn.execute(
        "DELETE FROM legislation_fts_zh WHERE rowid IN "
        "(SELECT id FROM legislation_sections WHERE doc_id=?)",
        (doc_id,),
    )
    conn.execute("DELETE FROM legislation_sections WHERE doc_id=?", (doc_id,))


def upsert_document(
    conn: sqlite3.Connection,
    doc: ParsedDocument,
    source_file: str,
    checksum: str,
) -> int:
    """Insert or replace one document and its sections; return the doc id."""
    row = conn.execute(
        "SELECT id FROM legislation_docs WHERE cap=? AND doc_type=? AND language=?",
        (doc.cap, doc.doc_type, doc.language),
    ).fetchone()
    values = (
        doc.cap,
        doc.doc_type,
        doc.doc_number,
        doc.doc_name,
        doc.title,
        doc.long_title,
        doc.language,
        doc.version_date,
        doc.status,
        _source_url(doc),
        source_file,
        checksum,
    )
    if row:
        doc_id = int(row["id"])
        _delete_document_sections(conn, doc_id)
        conn.execute(
            """
            UPDATE legislation_docs SET
                cap=?, doc_type=?, doc_number=?, doc_name=?, title=?, long_title=?,
                language=?, version_date=?, status=?, source_url=?, source_file=?,
                checksum=?, ingested_at=datetime('now')
            WHERE id=?
            """,
            values + (doc_id,),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO legislation_docs
                (cap, doc_type, doc_number, doc_name, title, long_title, language,
                 version_date, status, source_url, source_file, checksum)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            values,
        )
        doc_id = int(cur.lastrowid)

    fts_table = "legislation_fts_en" if doc.language == "en" else "legislation_fts_zh"
    for sec in doc.sections:
        cur = conn.execute(
            """
            INSERT INTO legislation_sections
                (doc_id, cap, doc_type, section_key, section_no, heading, text,
                 part, division, language, version_date, source_url, source_note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                doc.cap,
                doc.doc_type,
                sec.section_key,
                sec.section_no,
                sec.heading,
                sec.text,
                sec.part,
                sec.division,
                doc.language,
                doc.version_date,
                _source_url(doc),
                sec.source_note,
            ),
        )
        sid = int(cur.lastrowid)
        conn.execute(
            f"INSERT INTO {fts_table}(rowid, section_id, cap, section_no, heading, text) "
            "VALUES (?,?,?,?,?,?)",
            (sid, sid, doc.cap, sec.section_no, sec.heading or "", sec.text),
        )
    return doc_id


def _delete_history_document_sections(
    conn: sqlite3.Connection, doc_id: int
) -> None:
    conn.execute(
        "DELETE FROM legislation_history_sections WHERE doc_id=?", (doc_id,)
    )


def upsert_history_document(
    conn: sqlite3.Connection,
    doc: ParsedDocument,
    source_file: str,
    checksum: str,
) -> int:
    """Insert or replace one historical version and its sections."""
    row = conn.execute(
        "SELECT id FROM legislation_history_docs "
        "WHERE cap=? AND doc_type=? AND language=? AND version_date=?",
        (doc.cap, doc.doc_type, doc.language, doc.version_date),
    ).fetchone()
    values = (
        doc.cap,
        doc.doc_type,
        doc.doc_number,
        doc.doc_name,
        doc.title,
        doc.long_title,
        doc.language,
        doc.version_date,
        doc.status,
        _source_url(doc),
        source_file,
        checksum,
    )
    if row:
        doc_id = int(row["id"])
        _delete_history_document_sections(conn, doc_id)
        conn.execute(
            """
            UPDATE legislation_history_docs SET
                cap=?, doc_type=?, doc_number=?, doc_name=?, title=?, long_title=?,
                language=?, version_date=?, status=?, source_url=?, source_file=?,
                checksum=?, ingested_at=datetime('now')
            WHERE id=?
            """,
            values + (doc_id,),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO legislation_history_docs
                (cap, doc_type, doc_number, doc_name, title, long_title, language,
                 version_date, status, source_url, source_file, checksum)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            values,
        )
        doc_id = int(cur.lastrowid)

    for sec in doc.sections:
        conn.execute(
            """
            INSERT INTO legislation_history_sections
                (doc_id, cap, doc_type, section_key, section_no, heading, text,
                 part, division, language, version_date, source_url, source_note)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                doc_id,
                doc.cap,
                doc.doc_type,
                sec.section_key,
                sec.section_no,
                sec.heading,
                sec.text,
                sec.part,
                sec.division,
                doc.language,
                doc.version_date,
                _source_url(doc),
                sec.source_note,
            ),
        )
    return doc_id


def ingest_history_zip(
    conn: sqlite3.Connection,
    zip_path: Path,
    only_language: str | None = None,
    progress: Callable[[str], None] | None = None,
    skip_unchanged: bool = False,
) -> dict[str, int]:
    """Index the historical versions in a HKeL past-version ZIP archive."""
    counts = {"documents": 0, "sections": 0, "skipped": 0, "failed": 0}
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        for index, entry in enumerate(entries, start=1):
            try:
                data = zf.read(entry)
                doc = parse_document(data, source_file=f"{zip_path.name}:{entry}")
            except Exception as exc:
                counts["failed"] += 1
                if progress:
                    progress(f"failed {entry}: {exc}")
                continue
            if only_language and doc.language != only_language:
                counts["skipped"] += 1
                continue
            if not doc.sections or not doc.version_date:
                counts["skipped"] += 1
                continue
            checksum = hashlib.sha256(data).hexdigest()
            if skip_unchanged:
                existing = conn.execute(
                    "SELECT checksum FROM legislation_history_docs "
                    "WHERE cap=? AND doc_type=? AND language=? AND version_date=?",
                    (doc.cap, doc.doc_type, doc.language, doc.version_date),
                ).fetchone()
                if existing and existing["checksum"] == checksum:
                    counts["skipped"] += 1
                    continue
            upsert_history_document(conn, doc, f"{zip_path.name}:{entry}", checksum)
            counts["documents"] += 1
            counts["sections"] += len(doc.sections)
            if counts["documents"] % 100 == 0:
                conn.commit()
            if progress and index % 200 == 0:
                progress(
                    f"{zip_path.name}: {index}/{len(entries)} files, "
                    f"{counts['documents']} versions, {counts['sections']} sections"
                )
    conn.commit()
    return counts


def ingest_zip(
    conn: sqlite3.Connection,
    zip_path: Path,
    only_language: str | None = None,
    progress: Callable[[str], None] | None = None,
    skip_unchanged: bool = False,
) -> dict[str, int]:
    """Index every XML document in a HKeL ZIP archive."""
    counts = {"documents": 0, "sections": 0, "skipped": 0, "failed": 0}
    with zipfile.ZipFile(zip_path) as zf:
        entries = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        for index, entry in enumerate(entries, start=1):
            try:
                data = zf.read(entry)
                doc = parse_document(data, source_file=f"{zip_path.name}:{entry}")
            except Exception as exc:
                counts["failed"] += 1
                if progress:
                    progress(f"failed {entry}: {exc}")
                continue
            if only_language and doc.language != only_language:
                counts["skipped"] += 1
                continue
            if not doc.sections:
                counts["skipped"] += 1
                continue
            checksum = hashlib.sha256(data).hexdigest()
            if skip_unchanged:
                existing = conn.execute(
                    "SELECT checksum FROM legislation_docs "
                    "WHERE cap=? AND doc_type=? AND language=?",
                    (doc.cap, doc.doc_type, doc.language),
                ).fetchone()
                if existing and existing["checksum"] == checksum:
                    counts["skipped"] += 1
                    continue
            upsert_document(conn, doc, f"{zip_path.name}:{entry}", checksum)
            counts["documents"] += 1
            counts["sections"] += len(doc.sections)
            if progress and index % 200 == 0:
                progress(
                    f"{zip_path.name}: {index}/{len(entries)} files, "
                    f"{counts['documents']} documents, {counts['sections']} sections"
                )
    conn.commit()
    return counts


def ingest_archives(
    conn: sqlite3.Connection,
    paths: Iterable[Path],
    only_language: str | None = None,
    progress: Callable[[str], None] | None = None,
    skip_unchanged: bool = False,
) -> dict[str, int]:
    total = {"documents": 0, "sections": 0, "skipped": 0, "failed": 0}
    for path in paths:
        if progress:
            kind = "historical versions" if is_history_archive(path) else "current versions"
            progress(f"indexing {path.name} ({kind})")
        ingest = ingest_history_zip if is_history_archive(path) else ingest_zip
        counts = ingest(
            conn,
            path,
            only_language=only_language,
            progress=progress,
            skip_unchanged=skip_unchanged,
        )
        for key in total:
            total[key] += counts[key]
    return total
