import json
import zipfile

import pytest

from hk_criminal_law_mcp.db import stats
from hk_criminal_law_mcp.hklii import (
    CaseNotLocalError,
    get_case_paragraphs,
    get_judgment,
    search_cases,
)
from hk_criminal_law_mcp.ingest_legislation import ingest_zip
from hk_criminal_law_mcp.sync import (
    PermissionRequiredError,
    import_cases,
    sync_cases,
    sync_status,
)

from .test_legislation_xml import XML


CASE = {
    "citation": "[2021] HKCFA 1",
    "title": "HKSAR v TEST",
    "court": "Court of Final Appeal",
    "court_code": "HKCFA",
    "year": 2021,
    "number": "1",
    "judgment_date": "2021-01-12",
    "language": "en",
    "source_url": "https://example.invalid/cases/2021-hkcfa-1",
    "paragraphs": [
        {"number": "1", "text": "Bail conditions must be justified."},
        {"number": "2", "text": "The appeal is allowed."},
    ],
    "cited_cases": [{"citation": "[2020] HKCA 10"}],
}


def _write_jsonl(path, records):
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return path


def test_import_cases_jsonl_and_local_search(conn, tmp_path):
    path = _write_jsonl(tmp_path / "corpus.jsonl", [CASE])
    result = import_cases(conn, path, source="test-corpus", license="test-only")
    assert result["status"] == "ok"
    assert result["stats"]["imported"] == 1

    hits = search_cases(conn, "bail conditions", live=False)
    assert hits["count"] >= 1
    assert hits["results"][0]["citation"] == "[2021] HKCFA 1"

    paras = get_case_paragraphs(
        conn, "[2021] HKCFA 1", ["1", "2"], allow_live=False
    )
    assert [p["number"] for p in paras["paragraphs"]] == ["1", "2"]

    corpus = stats(conn)
    assert corpus["cases"] == 1
    assert corpus["case_paragraphs"] == 2
    assert corpus["case_sources"] == 1
    assert corpus["cases_by_court"].get("hkcfa") == 1


def test_import_cases_csv(conn, tmp_path):
    path = tmp_path / "corpus.csv"
    path.write_text(
        "citation,title,court_code,year,number,judgment_date,language,text\n"
        "[2024] HKDC 7,HKSAR v CSV, HKDC,2024,7,2024-02-01,en,"
        "The defendant was convicted after trial.\n",
        encoding="utf-8",
    )
    result = import_cases(conn, path, format="csv", source="csv-test")
    assert result["stats"]["imported"] == 1
    hit = get_judgment(conn, "[2024] HKDC 7", allow_live=False)
    assert hit["citation"] == "[2024] HKDC 7"
    assert "convicted after trial" in hit["text"]


def test_import_is_idempotent(conn, tmp_path):
    path = _write_jsonl(tmp_path / "corpus.jsonl", [CASE])
    import_cases(conn, path, source="test-corpus")
    import_cases(conn, path, source="test-corpus")
    corpus = stats(conn)
    assert corpus["cases"] == 1
    assert corpus["case_paragraphs"] == 2


def test_local_only_blocks_missing_case(conn, monkeypatch):
    monkeypatch.setenv("HK_LAW_LOCAL_ONLY", "1")
    with pytest.raises(CaseNotLocalError):
        get_judgment(conn, "[2021] HKCFA 999", allow_live=True)


def test_sync_cases_requires_permission(conn, monkeypatch):
    monkeypatch.delenv("HK_LAW_CASE_PERMISSION_REF", raising=False)
    with pytest.raises(PermissionRequiredError):
        sync_cases(conn, citations=["[2021] HKCFA 1"])


def test_sync_cases_requires_citation_list(conn):
    with pytest.raises(PermissionRequiredError):
        sync_cases(conn, citations=[], permission_ref="TEST-PERMISSION")


def test_sync_status_reports_provenance(conn, tmp_path):
    path = _write_jsonl(tmp_path / "corpus.jsonl", [CASE])
    import_cases(conn, path, source="test-corpus", license="test-only")
    status = sync_status(conn)
    assert status["cases"] == 1
    assert status["case_source_rows"][0]["source"] == "test-corpus"
    assert status["permission_configured"] is False


def test_skip_unchanged_legislation(conn, tmp_path):
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fixture.xml", XML)
    first = ingest_zip(conn, archive, skip_unchanged=True)
    assert first["documents"] == 1
    second = ingest_zip(conn, archive, skip_unchanged=True)
    assert second["documents"] == 0
    assert second["skipped"] == 1
