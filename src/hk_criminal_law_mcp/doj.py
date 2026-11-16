"""Hong Kong Department of Justice (DOJ) publications.

The DOJ publishes the Prosecution Code, the domestic-violence prosecution
policy, and related material at https://www.doj.gov.hk. This module indexes
those public documents locally so the MCP can retrieve the prosecutor's own
policy framework alongside legislation and judgments.

Design rules
------------
* A curated seed list, plus bounded discovery from the two publication index
  pages. The fetcher follows no arbitrary links and never crawls the site.
* Conditional GETs (``If-Modified-Since``), SHA-256 checksums, and a polite
  delay between requests.
* DOJ material is public government information but remains subject to the
  DOJ's terms. It is cached for research and is not redistributed by this
  project.
* Every result carries its source URL, page date, fetch date and checksum.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .config import (
    DOJ_BASE,
    DOJ_REQUEST_INTERVAL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)

DOJ_SOURCE = "hk-doj"
DOJ_LICENSE = (
    "Government of the Hong Kong SAR — public information. Verify against the "
    "DOJ source; cached for research and not redistributed."
)

CATEGORY_LABELS = {
    "prosecution_code": "Prosecution Code",
    "domestic_violence": "Domestic Violence Prosecution Policy",
}

_LANG_PREFIX = {"en": "en", "zh-Hant": "tc", "tc": "tc", "zh": "tc"}
_CONTENT_RE = re.compile(
    r"<!--\s*\*+\s*content starts\s*\*+\s*-->(.*?)"
    r"<!--\s*\*+\s*content ends\s*\*+\s*-->",
    re.S | re.I,
)
_PARA_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)[.)]?\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")


@dataclass(frozen=True)
class DojSeed:
    """One known DOJ publication page."""

    slug: str
    category: str
    title_en: str


PROSECUTION_CODE_TITLES = {
    "prosecution_intro": "Prosecution Code — Introduction",
    "prosecution_ch1": "Prosecution Code — Chapter 1: Independence of the Prosecutor",
    "prosecution_ch2": "Prosecution Code — Chapter 2: Director of Public Prosecutions",
    "prosecution_ch3": "Prosecution Code — Chapter 3: Role and Duties of the Prosecutor",
    "prosecution_ch4": "Prosecution Code — Chapter 4: Investigation and Prosecution",
    "prosecution_ch5": "Prosecution Code — Chapter 5: Decision to Prosecute",
    "prosecution_ch6": "Prosecution Code — Chapter 6: Consent to Prosecute",
    "prosecution_ch7": "Prosecution Code — Chapter 7: Private Prosecution",
    "prosecution_ch8": "Prosecution Code — Chapter 8: Charging Practice and Procedure",
    "prosecution_ch9": "Prosecution Code — Chapter 9: Proceeds of Crime",
    "prosecution_ch10": "Prosecution Code — Chapter 10: Review and Discontinuation",
    "prosecution_ch11": "Prosecution Code — Chapter 11: Immunity from Prosecution",
    "prosecution_ch12": "Prosecution Code — Chapter 12: Duty of Disclosure",
    "prosecution_ch13": "Prosecution Code — Chapter 13: Plea Negotiation and Agreement",
    "prosecution_ch14": "Prosecution Code — Chapter 14: Victims of Crime and Vulnerable Witnesses",
    "prosecution_ch15": "Prosecution Code — Chapter 15: Juvenile Offenders",
    "prosecution_ch16": "Prosecution Code — Chapter 16: Unrepresented Accused",
    "prosecution_ch17": "Prosecution Code — Chapter 17: Domestic Violence Cases",
    "prosecution_ch18": "Prosecution Code — Chapter 18: Human Exploitation Cases",
    "prosecution_ch19": "Prosecution Code — Chapter 19: Public Order Events",
    "prosecution_ch20": "Prosecution Code — Chapter 20: Expert Witnesses",
    "prosecution_ch21": "Prosecution Code — Chapter 21: Post-Conviction",
    "prosecution_ch22": "Prosecution Code — Chapter 22: Appeals and Reviews",
    "prosecution_ch23": "Prosecution Code — Chapter 23: Publication of Reasons",
    "prosecution_ch24": "Prosecution Code — Chapter 24: Media",
    "prosecution_app1": "Prosecution Code — Appendix 1: UN Guidelines on the Role of Prosecutors, 1990",
    "prosecution_app2": "Prosecution Code — Appendix 2: IAP Standards of Professional Responsibility",
}

DOMESTIC_VIOLENCE_TITLES = {
    "domesticviolence_1": "Domestic Violence Policy — Introduction",
    "domesticviolence_2": "Domestic Violence Policy — Definition of Domestic Violence",
    "domesticviolence_3": "Domestic Violence Policy — Role of the Department of Justice",
    "domesticviolence_4": "Domestic Violence Policy — Charging Policy",
    "domesticviolence_5": "Domestic Violence Policy — Charging Practice",
    "domesticviolence_6": "Domestic Violence Policy — The Reluctant Witness",
    "domesticviolence_7": "Domestic Violence Policy — When the Victim Withdraws Support",
    "domesticviolence_8": "Domestic Violence Policy — Prosecuting Against the Wishes of the Victim",
    "domesticviolence_9": "Domestic Violence Policy — Avoidance of Delay",
    "domesticviolence_10": "Domestic Violence Policy — Bail",
    "domesticviolence_11": "Domestic Violence Policy — Binding Over",
    "domesticviolence_12": "Domestic Violence Policy — Offence Against Public Justice",
    "domesticviolence_13": "Domestic Violence Policy — Support for Witness at Court",
    "domesticviolence_14": "Domestic Violence Policy — Status of Spouse",
    "domesticviolence_15": "Domestic Violence Policy — Sentencing",
    "domesticviolence_16": "Domestic Violence Policy — Conclusion",
    "domesticviolence_17": "Domestic Violence Policy — General",
}

SEEDS: tuple[DojSeed, ...] = tuple(
    [DojSeed(slug, "prosecution_code", title) for slug, title in PROSECUTION_CODE_TITLES.items()]
    + [DojSeed(slug, "domestic_violence", title) for slug, title in DOMESTIC_VIOLENCE_TITLES.items()]
)

_INDEXES = (
    ("prosecution_code", "prosecution_code", "prosecution_"),
    ("domesticviolence", "domestic_violence", "domesticviolence_"),
)


class DojError(RuntimeError):
    """Raised for unrecoverable DOJ ingestion problems."""


# ---------------------------------------------------------------------------
# HTML parsing and storage
# ---------------------------------------------------------------------------


def _clean_text(node) -> str:
    text = node.get_text("\n")
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _page_title(soup: BeautifulSoup) -> str | None:
    if not soup.title:
        return None
    title = " ".join(soup.title.get_text(" ", strip=True).split())
    return re.sub(r"^(Department of Justice|律政司)\s*-\s*", "", title)


def _content_block(html: str) -> str:
    match = _CONTENT_RE.search(html)
    return match.group(1) if match else html


def _version_date(soup: BeautifulSoup, html: str) -> str | None:
    meta = soup.find("meta", attrs={"name": "last-modified"})
    if meta and meta.get("content"):
        return str(meta["content"]).strip()[:10] or None
    match = re.search(r"revisionDate\s*=\s*'([^']+)'", html)
    return match.group(1).strip()[:10] if match else None


def _extract_paragraphs(content_soup: BeautifulSoup) -> list[dict]:
    """Split a DOJ page into paragraphs without inventing structure."""
    out: list[dict] = []
    ordinal = 0
    for element in content_soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        if element.find_parent(["p", "li"]):
            continue
        text = _clean_text(element)
        if not text:
            continue
        if text.upper() in {"PREVIOUS", "NEXT", "BACK"}:
            continue
        para_no: str | None = None
        heading: str | None = None
        if element.name in {"h1", "h2", "h3", "h4"}:
            heading = text
        else:
            match = _PARA_RE.match(text)
            if match:
                para_no = match.group(1)
            if element.name == "li":
                ordered = element.find_parent("ol")
                if ordered is not None and ordered.get("start"):
                    try:
                        start = int(ordered.get("start"))
                        siblings = ordered.find_all("li", recursive=False)
                        para_no = str(start + siblings.index(element))
                    except (TypeError, ValueError):
                        pass
        ordinal += 1
        out.append(
            {
                "para_no": para_no,
                "heading": heading,
                "text": text,
                "ordinal": ordinal,
            }
        )
    return out


def parse_doj_html(
    html: str,
    url: str,
    *,
    slug: str,
    category: str,
    language: str = "en",
    title: str | None = None,
    last_modified: str | None = None,
    etag: str | None = None,
) -> dict:
    """Parse one DOJ page into a storable document.

    ``title`` is the curated seed title for English pages. For Chinese pages the
    page's own title is used unless a curated title is supplied.
    """
    soup = BeautifulSoup(html, "lxml")
    parsed_title = _page_title(soup)
    if language == "en":
        doc_title = title or parsed_title or slug
    else:
        doc_title = parsed_title or title or slug
    content_html = _content_block(html)
    content_soup = BeautifulSoup(content_html, "lxml")
    for tag in content_soup.find_all(["script", "style"]):
        tag.decompose()
    for tag in content_soup.find_all("div"):
        classes = tag.get("class") or []
        if any("btnWrap" in value or "pagesCtrl" in value for value in classes):
            tag.decompose()

    paragraphs = _extract_paragraphs(content_soup)
    text = _clean_text(content_soup)
    if not text and paragraphs:
        text = "\n\n".join(item["text"] for item in paragraphs)
    checksum = hashlib.sha256(
        (content_html.strip() + "\n" + doc_title).encode("utf-8", errors="ignore")
    ).hexdigest()
    return {
        "slug": slug,
        "category": category,
        "title": doc_title,
        "language": language,
        "source_url": url,
        "source_file": f"{slug}.html",
        "version_date": _version_date(soup, html),
        "last_modified": last_modified,
        "etag": etag,
        "checksum": checksum,
        "html": content_html,
        "text": text,
        "paragraphs": paragraphs,
    }


def _fts_table(language: str) -> str:
    return "doj_fts_en" if language == "en" else "doj_fts_zh"


def store_doj_document(
    conn: sqlite3.Connection, document: dict, *, commit: bool = True
) -> int:
    """Upsert one DOJ document and replace its paragraphs and FTS rows."""
    conn.execute(
        """
        INSERT INTO doj_docs
            (slug, category, title, language, source_url, source_file,
             version_date, last_modified, etag, checksum, html, text, fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(slug, language) DO UPDATE SET
            category=excluded.category,
            title=excluded.title,
            source_url=excluded.source_url,
            source_file=excluded.source_file,
            version_date=excluded.version_date,
            last_modified=COALESCE(excluded.last_modified, doj_docs.last_modified),
            etag=COALESCE(excluded.etag, doj_docs.etag),
            checksum=excluded.checksum,
            html=excluded.html,
            text=excluded.text,
            fetched_at=excluded.fetched_at
        """,
        (
            document["slug"],
            document["category"],
            document["title"],
            document["language"],
            document["source_url"],
            document["source_file"],
            document.get("version_date"),
            document.get("last_modified"),
            document.get("etag"),
            document["checksum"],
            document.get("html"),
            document["text"],
        ),
    )
    row = conn.execute(
        "SELECT id FROM doj_docs WHERE slug=? AND language=?",
        (document["slug"], document["language"]),
    ).fetchone()
    if row is None:
        raise DojError(f"failed to store DOJ document {document['slug']!r}")
    doc_id = int(row["id"])
    fts = _fts_table(document["language"])
    conn.execute(f"DELETE FROM {fts} WHERE doc_id=?", (doc_id,))
    conn.execute("DELETE FROM doj_paragraphs WHERE doc_id=?", (doc_id,))
    for item in document.get("paragraphs", []):
        cursor = conn.execute(
            "INSERT INTO doj_paragraphs(doc_id, para_no, heading, text, ordinal) "
            "VALUES (?,?,?,?,?)",
            (
                doc_id,
                item.get("para_no"),
                item.get("heading"),
                item["text"],
                item.get("ordinal", 0),
            ),
        )
        conn.execute(
            f"INSERT INTO {fts}(paragraph_id, doc_id, slug, category, title, heading, text) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                int(cursor.lastrowid),
                doc_id,
                document["slug"],
                document["category"],
                document["title"],
                item.get("heading"),
                item["text"],
            ),
        )
    if commit:
        conn.commit()
    return doc_id


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


def _start_run(conn: sqlite3.Connection, kind: str, source: str) -> int:
    cursor = conn.execute(
        "INSERT INTO sync_runs(kind, source) VALUES (?,?)", (kind, source)
    )
    conn.commit()
    return int(cursor.lastrowid)


def _finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    status: str,
    stats: dict,
    error: str | None = None,
) -> None:
    import json

    conn.execute(
        "UPDATE sync_runs SET finished_at=datetime('now'), status=?, "
        "stats_json=?, error=? WHERE id=?",
        (status, json.dumps(stats, ensure_ascii=False), error, run_id),
    )
    conn.commit()


def _url(base_url: str, language: str, slug: str) -> str:
    prefix = _LANG_PREFIX.get(language, "en")
    return f"{base_url.rstrip('/')}/{prefix}/publications/{slug}.html"


def _throttle(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def discover_seeds(
    client: httpx.Client,
    base_url: str,
    language: str,
    *,
    request_interval: float,
    progress: Callable[[str], None] | None = None,
) -> list[DojSeed]:
    """Read the two DOJ index pages and return any additional pages.

    Discovery is deliberately shallow: it only reads links on the known index
    pages and only accepts the ``prosecution_`` and ``domesticviolence_``
    families. A failure returns an empty list; the curated seeds still run.
    """
    discovered: dict[str, DojSeed] = {}
    for index_slug, category, prefix in _INDEXES:
        url = _url(base_url, language, index_slug)
        if progress:
            progress(f"checking DOJ index {url}")
        try:
            response = client.get(url)
            response.raise_for_status()
        except Exception:
            _throttle(request_interval)
            continue
        soup = BeautifulSoup(response.text, "lxml")
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).split("#", 1)[0]
            if not href.endswith(".html"):
                continue
            slug = Path(href).stem
            if not slug.startswith(prefix):
                continue
            title = " ".join(anchor.get_text(" ", strip=True).split()) or slug
            discovered.setdefault(slug, DojSeed(slug, category, title))
        _throttle(request_interval)
    return list(discovered.values())


def sync_doj(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
    language: str = "en",
    base_url: str | None = None,
    progress: Callable[[str], None] | None = None,
    client: httpx.Client | None = None,
    seeds: Iterable[DojSeed] | None = None,
    request_interval: float | None = None,
) -> dict:
    """Incrementally update the local DOJ corpus.

    The default seed list covers the Prosecution Code and the domestic-violence
    prosecution policy. When ``seeds`` is omitted, the two index pages are also
    read to discover new pages. Conditional GETs and checksums skip unchanged
    documents.
    """
    language = "en" if language == "en" else "zh-Hant"
    base = (base_url or DOJ_BASE).rstrip("/")
    interval = (
        DOJ_REQUEST_INTERVAL_SECONDS if request_interval is None else request_interval
    )
    run_id = _start_run(conn, "doj_sync", "doj.gov.hk")
    counts = {
        "documents_checked": 0,
        "documents_updated": 0,
        "documents_unchanged": 0,
        "documents_failed": 0,
        "documents_discovered": 0,
        "paragraphs": 0,
    }
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
    try:
        selected: list[DojSeed]
        if seeds is None:
            selected = list(SEEDS)
            discovered = discover_seeds(
                client,
                base,
                language,
                request_interval=interval,
                progress=progress,
            )
            counts["documents_discovered"] = len(discovered)
            known = {seed.slug for seed in selected}
            selected.extend(seed for seed in discovered if seed.slug not in known)
        else:
            selected = list(seeds)

        for seed in selected:
            counts["documents_checked"] += 1
            url = _url(base, language, seed.slug)
            existing = conn.execute(
                "SELECT last_modified, checksum FROM doj_docs "
                "WHERE slug=? AND language=?",
                (seed.slug, language),
            ).fetchone()
            headers: dict[str, str] = {}
            if existing and existing["last_modified"] and not force:
                headers["If-Modified-Since"] = existing["last_modified"]
            try:
                response = client.get(url, headers=headers)
                if response.status_code == 304:
                    counts["documents_unchanged"] += 1
                    _throttle(interval)
                    continue
                if response.status_code == 404:
                    counts["documents_failed"] += 1
                    if progress:
                        progress(f"DOJ page not found: {url}")
                    _throttle(interval)
                    continue
                response.raise_for_status()
                document = parse_doj_html(
                    response.text,
                    url,
                    slug=seed.slug,
                    category=seed.category,
                    language=language,
                    title=seed.title_en,
                    last_modified=response.headers.get("last-modified"),
                    etag=response.headers.get("etag"),
                )
                if (
                    not force
                    and existing is not None
                    and existing["checksum"] == document["checksum"]
                ):
                    counts["documents_unchanged"] += 1
                    _throttle(interval)
                    continue
                store_doj_document(conn, document, commit=False)
                counts["documents_updated"] += 1
                counts["paragraphs"] += len(document.get("paragraphs", []))
                if progress:
                    progress(f"updated DOJ {seed.slug} ({len(document.get('paragraphs', []))} paragraphs)")
            except Exception as exc:
                counts["documents_failed"] += 1
                if progress:
                    progress(f"failed DOJ {seed.slug}: {exc}")
            _throttle(interval)

        conn.commit()
        status = "ok" if counts["documents_failed"] == 0 else "partial"
        if counts["documents_updated"] == 0 and counts["documents_failed"] == 0:
            status = "ok"
        doc_count = conn.execute("SELECT COUNT(*) FROM doj_docs").fetchone()[0]
        conn.execute(
            """
            INSERT INTO doj_sources(source, license, base_url, last_sync_at, doc_count)
            VALUES (?,?,?,datetime('now'),?)
            ON CONFLICT(source) DO UPDATE SET
                license=excluded.license,
                base_url=excluded.base_url,
                last_sync_at=excluded.last_sync_at,
                doc_count=excluded.doc_count
            """,
            (DOJ_SOURCE, DOJ_LICENSE, base, doc_count),
        )
        conn.commit()
        _finish_run(conn, run_id, status, counts)
        return {"status": status, "kind": "doj_sync", "stats": counts}
    except Exception as exc:
        _finish_run(conn, run_id, "failed", counts, str(exc))
        raise
    finally:
        if owns_client:
            client.close()


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def _match_query(query: str, language: str) -> str | None:
    query = query.strip()
    if not query:
        return None
    if language == "en":
        words = _WORD_RE.findall(query)
        if not words:
            return None
        return " AND ".join(f'"{word}"' for word in words)
    if len(query) < 3:
        return None
    return '"' + query.replace('"', '""') + '"'


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category)


def _citation(title: str, category: str, para_no: str | None) -> str:
    label = _category_label(category)
    short = title
    for prefix in ("Prosecution Code — ", "Domestic Violence Policy — "):
        if short.startswith(prefix):
            short = short[len(prefix):]
            break
    if para_no:
        return f"DOJ {label}, para {para_no}"
    return f"DOJ {label} — {short}"


def _row_to_doj(row: sqlite3.Row, include_text: bool, max_chars: int) -> dict:
    item = {
        "citation": _citation(row["title"], row["category"], row["para_no"]),
        "slug": row["slug"],
        "title": row["title"],
        "category": row["category"],
        "category_label": _category_label(row["category"]),
        "paragraph": row["para_no"],
        "heading": row["heading"],
        "language": row["language"],
        "version_date": row["version_date"],
        "source_url": row["source_url"],
        "snippet": row["snippet"],
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
    return item


def search_doj(
    conn: sqlite3.Connection,
    query: str,
    category: str | None = None,
    language: str = "en",
    limit: int = 8,
    include_text: bool = False,
    max_chars: int = 4000,
) -> dict:
    """Full-text search over the locally indexed DOJ publications."""
    language = "en" if language == "en" else "zh-Hant"
    limit = max(1, min(limit, 50))
    table = _fts_table(language)
    match = _match_query(query, language)
    rows: list[sqlite3.Row] = []
    if match:
        sql = f"""
            SELECT p.para_no, p.heading, d.slug, d.title, d.category,
                   d.language, d.version_date, d.source_url, p.text,
                   snippet({table}, 6, '[', ']', ' … ', 32) AS snippet,
                   bm25({table}) AS rank
            FROM {table}
            JOIN doj_paragraphs p ON p.id = {table}.paragraph_id
            JOIN doj_docs d ON d.id = p.doc_id
            WHERE {table} MATCH ? AND d.language = ?
        """
        params: list = [match, language]
        if category:
            sql += " AND d.category = ?"
            params.append(category)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            rows = []
    if not rows:
        like = f"%{query}%"
        sql = """
            SELECT p.para_no, p.heading, d.slug, d.title, d.category,
                   d.language, d.version_date, d.source_url, p.text,
                   substr(p.text, 1, 240) AS snippet
            FROM doj_paragraphs p
            JOIN doj_docs d ON d.id = p.doc_id
            WHERE d.language = ?
              AND (p.text LIKE ? OR p.heading LIKE ? OR d.title LIKE ?)
        """
        params = [language, like, like, like]
        if category:
            sql += " AND d.category = ?"
            params.append(category)
        sql += " LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()

    results = [_row_to_doj(row, include_text, max_chars) for row in rows]
    return {
        "query": query,
        "count": len(results),
        "results": results,
        "corpus": (
            "Hong Kong Department of Justice publications: Prosecution Code and "
            "domestic-violence prosecution policy (public policy material)"
        ),
        "warning": (
            "DOJ publications are policy material, not legislation or judgments. "
            "Read the full page and verify against the DOJ source before relying on it."
        ),
    }


def _normalise_slug(value: str) -> str:
    value = value.strip()
    if value.startswith("http://") or value.startswith("https://"):
        value = urlparse(value).path
    if value.endswith(".html"):
        value = Path(value).stem
    return value.rsplit("/", 1)[-1]


def _para_key(value: str | None) -> tuple[int, ...] | None:
    if not value:
        return None
    try:
        return tuple(int(part) for part in str(value).split("."))
    except ValueError:
        return None


def _para_selected(para_no: str | None, wanted: Iterable[str]) -> bool:
    if not para_no:
        return False
    key = _para_key(para_no)
    for spec in wanted:
        spec = str(spec).strip()
        if not spec:
            continue
        if "-" in spec:
            start, _, end = spec.partition("-")
            low, high = _para_key(start), _para_key(end)
            if low is not None and high is not None and key is not None:
                if low <= key <= high:
                    return True
        if para_no == spec:
            return True
    return False


def get_doj_document(
    conn: sqlite3.Connection,
    slug: str,
    language: str = "en",
    paragraphs: Iterable[str] | None = None,
    max_chars: int = 20000,
) -> dict:
    """Return a DOJ document, optionally filtered to specific paragraph numbers."""
    language = "en" if language == "en" else "zh-Hant"
    slug = _normalise_slug(slug)
    row = conn.execute(
        "SELECT * FROM doj_docs WHERE slug=? AND language=?", (slug, language)
    ).fetchone()
    if row is None:
        return {
            "found": False,
            "slug": slug,
            "language": language,
            "corpus": "Hong Kong Department of Justice publications",
            "hint": "Run hk-law sync-doj, or check the slug with list_doj_documents.",
        }
    para_rows = conn.execute(
        "SELECT para_no, heading, text, ordinal FROM doj_paragraphs "
        "WHERE doc_id=? ORDER BY ordinal",
        (row["id"],),
    ).fetchall()
    if paragraphs:
        wanted = list(paragraphs)
        para_rows = [item for item in para_rows if _para_selected(item["para_no"], wanted)]
    items = [
        {
            "paragraph": item["para_no"],
            "heading": item["heading"],
            "text": item["text"],
        }
        for item in para_rows
    ]
    if paragraphs:
        text = "\n\n".join(item["text"] for item in items)
        truncated = False
    else:
        text = row["text"] or ""
        truncated = False
        if len(text) > max_chars:
            text = text[:max_chars]
            truncated = True
    result = {
        "found": True,
        "citation": _citation(row["title"], row["category"], None),
        "slug": row["slug"],
        "title": row["title"],
        "category": row["category"],
        "category_label": _category_label(row["category"]),
        "language": row["language"],
        "version_date": row["version_date"],
        "source_url": row["source_url"],
        "fetched_at": row["fetched_at"],
        "verified": "local_corpus",
        "text": text,
        "truncated": truncated,
        "paragraphs": items,
        "corpus": "Hong Kong Department of Justice publications",
    }
    if paragraphs:
        result["note"] = (
            "Paragraph filtering returns the numbered rows. Unnumbered sub-items "
            "may be separate rows; omit the paragraphs argument for the full page."
        )
    if truncated:
        result["full_text_chars"] = len(row["text"] or "")
    return result


def list_doj_documents(
    conn: sqlite3.Connection,
    category: str | None = None,
    language: str = "en",
    limit: int = 200,
) -> dict:
    """List indexed DOJ documents with paragraph counts."""
    language = "en" if language == "en" else "zh-Hant"
    limit = max(1, min(limit, 500))
    sql = """
        SELECT d.slug, d.title, d.category, d.language, d.version_date,
               d.source_url, d.fetched_at, COUNT(p.id) AS paragraphs
        FROM doj_docs d
        LEFT JOIN doj_paragraphs p ON p.doc_id = d.id
        WHERE d.language = ?
    """
    params: list = [language]
    if category:
        sql += " AND d.category = ?"
        params.append(category)
    sql += " GROUP BY d.id ORDER BY d.category, d.slug LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    results = [
        {
            "slug": row["slug"],
            "title": row["title"],
            "category": row["category"],
            "category_label": _category_label(row["category"]),
            "language": row["language"],
            "version_date": row["version_date"],
            "source_url": row["source_url"],
            "fetched_at": row["fetched_at"],
            "paragraphs": row["paragraphs"],
        }
        for row in rows
    ]
    return {
        "count": len(results),
        "results": results,
        "categories": [
            {"category": key, "label": value}
            for key, value in CATEGORY_LABELS.items()
        ],
    }


def doj_status(conn: sqlite3.Connection) -> dict:
    """Return DOJ corpus counts, freshness and provenance."""
    def one(sql: str, *args):
        row = conn.execute(sql, args).fetchone()
        return row[0] if row else 0

    documents = one("SELECT COUNT(*) FROM doj_docs")
    paragraphs = one("SELECT COUNT(*) FROM doj_paragraphs")
    by_category = {
        row["category"]: row["n"]
        for row in conn.execute(
            "SELECT category, COUNT(*) AS n FROM doj_docs GROUP BY category"
        ).fetchall()
    }
    by_language = {
        row["language"]: row["n"]
        for row in conn.execute(
            "SELECT language, COUNT(*) AS n FROM doj_docs GROUP BY language"
        ).fetchall()
    }
    latest = one("SELECT MAX(version_date) FROM doj_docs")
    last_sync = one(
        "SELECT MAX(finished_at) FROM sync_runs WHERE kind='doj_sync' "
        "AND status IN ('ok','partial')"
    )
    age_row = conn.execute(
        "SELECT (julianday('now') - julianday(MAX(finished_at))) AS days "
        "FROM sync_runs WHERE kind='doj_sync' AND status IN ('ok','partial')"
    ).fetchone()
    age_days = age_row["days"] if age_row else None
    sources = [
        dict(row)
        for row in conn.execute(
            "SELECT source, license, base_url, last_sync_at, doc_count "
            "FROM doj_sources ORDER BY source"
        ).fetchall()
    ]
    gaps: list[str] = []
    if not documents:
        gaps.append("DOJ corpus is empty. Run: hk-law sync-doj")
    elif age_days is not None and age_days > 30:
        gaps.append(
            f"DOJ corpus was last synced {int(age_days)} days ago. Run: hk-law sync-doj"
        )
    if documents and not by_category.get("prosecution_code"):
        gaps.append("DOJ Prosecution Code is missing. Run: hk-law sync-doj")
    if documents and not by_category.get("domestic_violence"):
        gaps.append("DOJ domestic-violence policy is missing. Run: hk-law sync-doj")
    return {
        "documents": documents,
        "paragraphs": paragraphs,
        "by_category": by_category,
        "by_language": by_language,
        "latest_version_date": latest,
        "last_sync": last_sync,
        "last_sync_age_days": age_days,
        "sources": sources,
        "gaps": gaps,
    }


_DOJ_CITE_RE = re.compile(
    r"(prosecution\s+code|domestic\s+violence(?:\s+(?:policy|prosecution\s+policy))?"
    r"|檢控守則|家庭暴力(?:政策)?|檢控涉及家庭暴力案件的政策)"
    r"[^0-9]{0,40}(\d+(?:\.\d+)*)",
    re.I,
)


def verify_doj_citation(
    conn: sqlite3.Connection,
    citation: str,
    category: str | None = None,
    language: str = "en",
) -> dict:
    """Verify a DOJ citation such as ``Prosecution Code §5.9`` or ``Domestic
    Violence Policy para 14`` against the local DOJ corpus."""
    language = "en" if language == "en" else "zh-Hant"
    text = citation.strip()
    match = _DOJ_CITE_RE.search(text)
    if match is None:
        return {
            "status": "unrecognised",
            "type": "doj",
            "citation": citation,
            "hint": "Use 'Prosecution Code §5.9' or 'Domestic Violence Policy para 14'.",
        }
    if category is None:
        low = text.lower()
        if "prosecution" in low or "檢控守則" in text:
            category = "prosecution_code"
        elif "domestic" in low or "家庭暴力" in text:
            category = "domestic_violence"
    para_no = match.group(2)
    sql = """
        SELECT p.para_no, p.heading, p.text, d.slug, d.title, d.category,
               d.version_date, d.source_url
        FROM doj_paragraphs p
        JOIN doj_docs d ON d.id = p.doc_id
        WHERE p.para_no = ? AND d.language = ?
    """
    params: list = [para_no, language]
    if category:
        sql += " AND d.category = ?"
        params.append(category)
    sql += " ORDER BY d.category, d.slug LIMIT 20"
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return {
            "status": "not_found",
            "type": "doj",
            "citation": citation,
            "paragraph": para_no,
            "category": category,
            "language": language,
        }
    return {
        "status": "verified",
        "type": "doj",
        "citation": citation,
        "paragraph": para_no,
        "category": category,
        "language": language,
        "matches": [
            {
                "citation": _citation(row["title"], row["category"], row["para_no"]),
                "paragraph": row["para_no"],
                "slug": row["slug"],
                "title": row["title"],
                "category": row["category"],
                "category_label": _category_label(row["category"]),
                "heading": row["heading"],
                "version_date": row["version_date"],
                "source_url": row["source_url"],
                "snippet": (row["text"] or "")[:300],
            }
            for row in rows
        ],
        "warning": (
            "Verified against the local DOJ corpus. Read the full paragraph in "
            "context; policy material is not legislation."
        ),
    }
