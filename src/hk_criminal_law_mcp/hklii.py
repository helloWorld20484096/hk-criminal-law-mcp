"""HKLII retrieval client with local caching and polite rate limiting.

HKLII (https://www.hklii.hk) is a free public legal information service. The
JSON endpoints used here are the ones its own web client uses. They are not a
documented public API and may change. Judgments remain subject to the terms of
HKLII and the Hong Kong Judiciary; this project caches them locally for
research and does not redistribute them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
from bs4 import BeautifulSoup

from .citations import (
    COURT_CODES,
    COURT_NAMES,
    CaseCitation,
    parse_case_citation,
)
from .config import (
    HKLII_BASE,
    REQUEST_INTERVAL_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
    local_only,
)

ABBR_TO_CODE = {
    "hkcfa": "HKCFA",
    "hkca": "HKCA",
    "hkcfi": "HKCFI",
    "hkdc": "HKDC",
    "hkmagc": "HKMC",
    "hkct": "HKCT",
    "hkfc": "HKFC",
    "hkldt": "HKLdT",
    "hksct": "HKSCT",
    "hkcrc": "HKCRC",
    "hkoat": "HKOAT",
    "hklat": "HKLAT",
}

_CASE_PATH_RE = re.compile(r"/(en|tc)/cases/([a-z]+)/(\d{4})/(\d+)\b")
_LANG_PATH = {"en": "en", "zh-Hant": "tc", "tc": "tc"}

_rate_lock = threading.Lock()
_last_request = 0.0


class HKLIIError(RuntimeError):
    pass


class CaseNotLocalError(RuntimeError):
    """Raised when a case is absent locally and live access is not permitted."""


def _throttle() -> None:
    global _last_request
    with _rate_lock:
        wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _get_json(path: str, params: dict[str, Any]) -> Any:
    url = f"{HKLII_BASE}/{path.lstrip('/')}"
    last_error: Exception | None = None
    for attempt in range(3):
        _throttle()
        try:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                    "Referer": f"{HKLII_BASE}/en/",
                },
            ) as client:
                response = client.get(url, params=params)
            if response.status_code in {429, 500, 502, 503, 504}:
                raise HKLIIError(f"HKLII returned HTTP {response.status_code}")
            response.raise_for_status()
            text = response.text.strip()
            if not text:
                return None
            return response.json()
        except Exception as exc:  # network or JSON failure
            last_error = exc
            time.sleep(2 ** attempt)
    raise HKLIIError(f"HKLII request failed: {url} ({last_error})")


def _cache_ttl() -> int:
    try:
        return int(os.environ.get("HK_LAW_CACHE_TTL", "21600"))
    except ValueError:
        return 21600


def _cache_get(conn: sqlite3.Connection, key: str) -> Any | None:
    row = conn.execute(
        "SELECT payload, fetched_at FROM case_search_cache WHERE query_key=?", (key,)
    ).fetchone()
    if not row:
        return None
    age = conn.execute(
        "SELECT (julianday('now') - julianday(?)) * 86400", (row["fetched_at"],)
    ).fetchone()[0]
    if age is None or age > _cache_ttl():
        return None
    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        return None


def _cache_put(conn: sqlite3.Connection, key: str, payload: Any) -> None:
    conn.execute(
        "INSERT INTO case_search_cache(query_key, payload, fetched_at) "
        "VALUES (?,?,datetime('now')) "
        "ON CONFLICT(query_key) DO UPDATE SET payload=excluded.payload, "
        "fetched_at=datetime('now')",
        (key, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()


def _result_court_key(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.upper() in COURT_CODES:
        return COURT_CODES[value.upper()]
    lowered = value.lower()
    if lowered in COURT_NAMES:
        return lowered
    for abbr, name in COURT_NAMES.items():
        if value.lower() in name.lower():
            return abbr
    return None


def _parse_search_result(raw: dict, lang_pref: str = "en") -> dict | None:
    path = raw.get("path") or ""
    m = _CASE_PATH_RE.search(path)
    if not m:
        return None
    path_lang, abbr, year, num = m.groups()
    code = ABBR_TO_CODE.get(abbr)
    if not code:
        return None
    citation = f"[{year}] {code} {num}"
    language = "en" if path_lang == "en" else "zh-Hant"
    return {
        "citation": citation,
        "title": (raw.get("title") or "").strip(),
        "court": raw.get("db"),
        "court_abbr": abbr,
        "year": int(year),
        "number": num,
        "language": language,
        "source_url": f"{HKLII_BASE}{path}",
        "published": raw.get("pub_date"),
        "path": path,
        "preferred": language == ("zh-Hant" if lang_pref in {"tc", "zh-Hant"} else "en"),
    }


def _search_live(
    query: str,
    court: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 20,
    lang: str = "en",
    conn: sqlite3.Connection | None = None,
) -> dict:
    cache_key = hashlib.sha256(
        json.dumps(
            {
                "q": query,
                "court": court,
                "from": year_from,
                "to": year_to,
                "lang": lang,
                "limit": limit,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    if conn is not None:
        cached = _cache_get(conn, cache_key)
        if cached is not None:
            cached["source"] = "hklii_cache"
            return cached

    payload = _get_json("api/simplesearch", {"searchstring": query})
    if not payload:
        result = {
            "query": query,
            "count": 0,
            "results": [],
            "source": "hklii_live",
            "warning": "HKLII returned no payload; the endpoint may be unavailable or rate-limited.",
        }
        if conn is not None:
            _cache_put(conn, cache_key, result)
        return result

    court_key = _result_court_key(court)
    results: list[dict] = []
    for raw in payload.get("results", []):
        parsed = _parse_search_result(raw, lang_pref=lang)
        if not parsed:
            continue
        if court_key and parsed["court_abbr"] != court_key:
            continue
        if year_from and parsed["year"] < year_from:
            continue
        if year_to and parsed["year"] > year_to:
            continue
        results.append(parsed)

    # Deduplicate by citation, preferring the requested language.
    chosen: dict[str, dict] = {}
    for item in results:
        current = chosen.get(item["citation"])
        if current is None or (item["preferred"] and not current["preferred"]):
            chosen[item["citation"]] = item
    ordered = sorted(
        chosen.values(), key=lambda r: (r["year"], int(r["number"])), reverse=True
    )
    result = {
        "query": query,
        "count": len(ordered),
        "results": ordered[: max(1, min(limit, 100))],
        "source": "hklii_live",
        "endpoint": f"{HKLII_BASE}/api/simplesearch",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if conn is not None:
        _cache_put(conn, cache_key, result)
    return result


def _search_local(
    conn: sqlite3.Connection,
    query: str,
    court: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 20,
    lang: str = "en",
) -> list[dict]:
    table = "cases_fts_en" if lang == "en" else "cases_fts_zh"
    words = re.findall(r"[A-Za-z0-9']+", query)
    if lang == "en" and words:
        match = " AND ".join(f'"{w}"' for w in words)
    else:
        match = f'"{query}"'
    try:
        rows = conn.execute(
            f"""
            SELECT c.neutral_citation, c.title, c.court, c.court_code, c.year, c.num,
                   c.language, c.source_url,
                   snippet({table}, 3, '[', ']', ' … ', 24) AS snip,
                   bm25({table}) AS rank
            FROM {table}
            JOIN cases c ON c.id = {table}.case_id
            WHERE {table} MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    court_key = _result_court_key(court)
    out = []
    for row in rows:
        if court_key and row["court_code"] != court_key:
            continue
        if year_from and (row["year"] or 0) < year_from:
            continue
        if year_to and (row["year"] or 0) > year_to:
            continue
        out.append(
            {
                "citation": row["neutral_citation"],
                "title": row["title"],
                "court": row["court"],
                "court_code": row["court_code"],
                "court_abbr": row["court_code"],
                "year": row["year"],
                "number": row["num"],
                "language": row["language"],
                "source_url": row["source_url"],
                "snippet": row["snip"],
                "cached": True,
            }
        )
    return out


def search_cases(
    conn: sqlite3.Connection,
    query: str,
    court: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 20,
    lang: str = "en",
    live: bool = False,
) -> dict:
    """Search local judgments and, by default, the live HKLII database.

    A live failure is non-fatal: local results are returned with `live_error`.
    """
    local = _search_local(conn, query, court, year_from, year_to, limit, lang)
    live_result = {"source": "disabled", "results": [], "count": 0}
    live_error = None
    if live:
        try:
            live_result = _search_live(
                query, court, year_from, year_to, limit, lang, conn
            )
        except Exception as exc:
            live_error = str(exc)
            live_result = {
                "source": "hklii_error",
                "results": [],
                "count": 0,
                "error": live_error,
            }
    seen = {item["citation"] for item in local}
    merged = list(local)
    for item in live_result.get("results", []):
        if item["citation"] not in seen:
            merged.append(item)
            seen.add(item["citation"])
    return {
        "query": query,
        "count": len(merged),
        "results": merged[: max(1, min(limit, 100))],
        "local_count": len(local),
        "live_source": live_result.get("source"),
        "live_error": live_error,
        "warning": (
            "Local results only; no live HKLII search was performed. Verify each "
            "citation in the Judiciary's Legal Reference System or the official "
            "judgment text."
            if not live
            else "HKLII search is an unofficial endpoint. Verify each citation in "
            "the Judiciary's Legal Reference System or the official judgment text."
        ),
    }


def _parse_judgment_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = re.sub(r"\s+", " ", soup.title.string).strip()

    paragraphs: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", class_="para"):
        number = (anchor.get("id") or "").lstrip("p") or (anchor.get("name") or "").lstrip("p")
        parent = anchor.find_parent("p")
        if not number or parent is None:
            continue
        text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True)).strip()
        text = re.sub(rf"^{re.escape(number)}\.?\s*", "", text)
        if not text or number in seen:
            continue
        seen.add(number)
        paragraphs.append({"number": number, "text": text})

    if not paragraphs:
        body = soup.body or soup
        text = re.sub(r"\n{2,}", "\n", body.get_text("\n", strip=True))
        paragraphs = [
            {"number": str(i), "text": line.strip()}
            for i, line in enumerate(text.splitlines(), start=1)
            if line.strip()
        ]

    full_text = "\n\n".join(f"{p['number']}. {p['text']}" for p in paragraphs)
    return {"title": title, "paragraphs": paragraphs, "text": full_text}


def _case_row_to_dict(row: sqlite3.Row, include_text: bool = True) -> dict:
    paragraphs = json.loads(row["paragraphs_json"]) if row["paragraphs_json"] else []
    cited = json.loads(row["cited_cases_json"]) if row["cited_cases_json"] else []
    out = {
        "citation": row["neutral_citation"],
        "title": row["title"],
        "court": row["court"],
        "court_code": row["court_code"],
        "judgment_date": row["judgment_date"],
        "language": row["language"],
        "source_url": row["source_url"],
        "official_document": row["doc_url"],
        "paragraphs": paragraphs,
        "cited_cases": cited,
        "parallel_citation": row["parallel_citation"],
        "is_translation": bool(row["is_translation"]),
        "has_translation": bool(row["has_translation"]),
        "fetched_at": row["fetched_at"],
        "cached": True,
    }
    if include_text:
        out["text"] = row["text"]
    return out


def store_case(
    conn: sqlite3.Connection,
    citation: str,
    meta: dict,
    parsed: dict,
    language: str,
    court_code: str,
    year: int,
    number: str,
    html: str,
    checksum: str,
    source_url: str | None = None,
    commit: bool = True,
) -> int:
    row = conn.execute(
        "SELECT id FROM cases WHERE neutral_citation=? AND language=?",
        (citation, language),
    ).fetchone()
    parallel = meta.get("parallel_citation")
    if isinstance(parallel, (list, dict)):
        parallel = json.dumps(parallel, ensure_ascii=False)
    source_url = source_url or (
        f"{HKLII_BASE}/{'tc' if language != 'en' else 'en'}/cases/"
        f"{court_code}/{year}/{number}"
    )
    values = (
        citation,
        meta.get("db"),
        court_code,
        year,
        number,
        parsed.get("title"),
        meta.get("date"),
        language,
        source_url,
        meta.get("doc"),
        html,
        parsed.get("text"),
        json.dumps(parsed.get("paragraphs", []), ensure_ascii=False),
        json.dumps(meta.get("cases", []), ensure_ascii=False),
        parallel,
        int(bool(meta.get("is_translation"))),
        int(bool(meta.get("has_translation"))),
        checksum,
    )
    if row:
        case_id = int(row["id"])
        conn.execute(
            """
            UPDATE cases SET court=?, court_code=?, year=?, num=?, title=?,
                judgment_date=?, language=?, source_url=?, doc_url=?, html=?,
                text=?, paragraphs_json=?, cited_cases_json=?, parallel_citation=?,
                is_translation=?, has_translation=?, fetched_at=datetime('now'),
                checksum=?
            WHERE id=?
            """,
            values[1:] + (case_id,),
        )
    else:
        cur = conn.execute(
            """
            INSERT INTO cases
                (neutral_citation, court, court_code, year, num, title,
                 judgment_date, language, source_url, doc_url, html, text,
                 paragraphs_json, cited_cases_json, parallel_citation,
                 is_translation, has_translation, checksum)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            values,
        )
        case_id = int(cur.lastrowid)

    for table in ("cases_fts_en", "cases_fts_zh"):
        conn.execute(f"DELETE FROM {table} WHERE rowid=?", (case_id,))
    conn.execute("DELETE FROM case_paragraphs WHERE case_id=?", (case_id,))
    for para in parsed.get("paragraphs", []):
        conn.execute(
            "INSERT OR REPLACE INTO case_paragraphs(case_id, para_no, text) VALUES (?,?,?)",
            (case_id, para["number"], para["text"]),
        )
    fts = "cases_fts_en" if language == "en" else "cases_fts_zh"
    conn.execute(
        f"INSERT INTO {fts}(rowid, case_id, neutral_citation, title, text) VALUES (?,?,?,?,?)",
        (case_id, case_id, citation, parsed.get("title") or "", parsed.get("text") or ""),
    )
    if commit:
        conn.commit()
    return case_id


def get_judgment(
    conn: sqlite3.Connection,
    citation: str,
    lang: str = "en",
    force: bool = False,
    allow_live: bool = True,
) -> dict:
    """Return a judgment from the local corpus, optionally fetching it live.

    ``allow_live=False`` (or ``HK_LAW_LOCAL_ONLY=1``) makes the function
    strictly local: a missing case raises :class:`CaseNotLocalError` instead of
    contacting HKLII.
    """
    parsed_cit = parse_case_citation(citation)
    if not parsed_cit or not parsed_cit.court_abbr:
        raise HKLIIError(f"Unrecognised Hong Kong neutral citation: {citation}")
    language = "en" if lang == "en" else "zh-Hant"
    normalised = parsed_cit.normalised
    row = conn.execute(
        "SELECT * FROM cases WHERE neutral_citation=? AND language=?",
        (normalised, language),
    ).fetchone()
    if row and (not force or local_only()):
        return _case_row_to_dict(row)

    if local_only() or not allow_live:
        raise CaseNotLocalError(
            f"{normalised} ({language}) is not in the local judgment corpus. "
            "Import an authorized corpus, or set allow_live=True only when a "
            "permitted live source is configured."
        )

    payload = _get_json(
        "api/getjudgment",
        {
            "lang": _LANG_PATH.get(language, "en"),
            "abbr": parsed_cit.court_abbr,
            "year": parsed_cit.year,
            "num": parsed_cit.number,
        },
    )
    if not payload or not payload.get("content"):
        raise HKLIIError(f"No judgment returned for {normalised}")
    html = payload["content"]
    parsed = _parse_judgment_html(html)
    checksum = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
    store_case(
        conn,
        normalised,
        payload,
        parsed,
        language,
        parsed_cit.court_abbr,
        parsed_cit.year,
        parsed_cit.number,
        html,
        checksum,
    )
    row = conn.execute(
        "SELECT * FROM cases WHERE neutral_citation=? AND language=?",
        (normalised, language),
    ).fetchone()
    result = _case_row_to_dict(row)
    result["cached"] = False
    return result


def get_case_paragraphs(
    conn: sqlite3.Connection,
    citation: str,
    numbers: list[str],
    lang: str = "en",
    allow_live: bool = True,
) -> dict:
    """Return selected paragraphs, fetching the judgment first if permitted."""
    get_judgment(conn, citation, lang=lang, allow_live=allow_live)
    language = "en" if lang == "en" else "zh-Hant"
    row = conn.execute(
        "SELECT id FROM cases WHERE neutral_citation=? AND language=?",
        (parse_case_citation(citation).normalised, language),
    ).fetchone()
    if not row:
        raise HKLIIError(f"Case not cached: {citation}")
    case_id = int(row["id"])
    expanded: list[str] = []
    for item in numbers:
        item = str(item).strip().lstrip("p")
        m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", item)
        if m:
            expanded.extend(str(n) for n in range(int(m.group(1)), int(m.group(2)) + 1))
        elif item:
            expanded.append(item)
    found = []
    missing = []
    for number in dict.fromkeys(expanded):
        para = conn.execute(
            "SELECT para_no, text FROM case_paragraphs WHERE case_id=? AND para_no=?",
            (case_id, number),
        ).fetchone()
        if para:
            found.append({"number": para["para_no"], "text": para["text"]})
        else:
            missing.append(number)
    return {
        "citation": citation,
        "requested": numbers,
        "paragraphs": found,
        "missing": missing,
    }


def note_up(
    conn: sqlite3.Connection,
    citation: str,
    force: bool = False,
    allow_live: bool = True,
) -> dict:
    """Return HKLII's note-up data (documents citing this judgment)."""
    parsed = parse_case_citation(citation)
    if not parsed or not parsed.court_abbr:
        raise HKLIIError(f"Unrecognised Hong Kong neutral citation: {citation}")
    normalised = parsed.normalised
    row = conn.execute(
        "SELECT id FROM cases WHERE neutral_citation=? LIMIT 1", (normalised,)
    ).fetchone()
    if row:
        cached = conn.execute(
            "SELECT payload, fetched_at FROM case_noteups WHERE case_id=?", (row["id"],)
        ).fetchone()
        if cached and (not force or local_only()):
            return {
                "citation": normalised,
                "payload": json.loads(cached["payload"]),
                "fetched_at": cached["fetched_at"],
                "cached": True,
            }
    if local_only() or not allow_live:
        raise CaseNotLocalError(
            f"No cached note-up data for {normalised}. Import the case or enable "
            "live note-up only with a permitted source."
        )
    payload = _get_json(
        "api/getcasenoteup",
        {
            "abbr": parsed.court_abbr,
            "year": parsed.year,
            "num": parsed.number,
        },
    )
    if row:
        conn.execute(
            "INSERT INTO case_noteups(case_id, payload, fetched_at) "
            "VALUES (?,?,datetime('now')) "
            "ON CONFLICT(case_id) DO UPDATE SET payload=excluded.payload, "
            "fetched_at=datetime('now')",
            (row["id"], json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
    return {
        "citation": normalised,
        "payload": payload,
        "cached": False,
        "warning": "Note-up data is a research aid, not a citator of record.",
    }
