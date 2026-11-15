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

ARCHIVES: dict[tuple[str, str], str] = {
    ("1-300", "en"): "hkel_c_leg_cap_1_cap_300_en.zip",
    ("301-600", "en"): "hkel_c_leg_cap_301_cap_600_en.zip",
    ("601+", "en"): "hkel_c_leg_cap_601_cap_end_en.zip",
    ("instruments", "en"): "hkel_c_instruments_en.zip",
    ("1-300", "zh-Hant"): "hkel_c_leg_cap_1_cap_300_zh-Hant.zip",
    ("301-600", "zh-Hant"): "hkel_c_leg_cap_301_cap_600_zh-Hant.zip",
    ("601+", "zh-Hant"): "hkel_c_leg_cap_601_cap_end_zh-Hant.zip",
    ("instruments", "zh-Hant"): "hkel_c_instruments_zh-Hant.zip",
}


def archive_url(filename: str) -> str:
    return f"{DATA_GOV_BASE}/{filename}"


def download_archives(
    dest: Path,
    languages: Iterable[str] = ("en", "zh-Hant"),
    ranges: Iterable[str] = ("1-300", "301-600", "601+", "instruments"),
    force: bool = False,
    progress: Callable[[str], None] | None = None,
) -> list[Path]:
    """Download official HKeL current-version ZIP archives.

    Files come from DATA.GOV.HK (Hong Kong Department of Justice). Reuse is
    subject to the DATA.GOV.HK terms of use; attribution is required.
    """
    dest.mkdir(parents=True, exist_ok=True)
    wanted = [(r, lang) for lang in languages for r in ranges]
    out: list[Path] = []
    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for rng, lang in wanted:
            filename = ARCHIVES.get((rng, lang))
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


def ingest_zip(
    conn: sqlite3.Connection,
    zip_path: Path,
    only_language: str | None = None,
    progress: Callable[[str], None] | None = None,
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
) -> dict[str, int]:
    total = {"documents": 0, "sections": 0, "skipped": 0, "failed": 0}
    for path in paths:
        if progress:
            progress(f"indexing {path.name}")
        counts = ingest_zip(conn, path, only_language=only_language, progress=progress)
        for key in total:
            total[key] += counts[key]
    return total
