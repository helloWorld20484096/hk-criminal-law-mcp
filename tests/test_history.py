from hk_criminal_law_mcp.ingest_legislation import (
    upsert_document,
    upsert_history_document,
)
from hk_criminal_law_mcp.legislation_xml import parse_document
from hk_criminal_law_mcp.search import (
    get_section_range,
    get_statute_history,
    list_section_versions,
    section_sort_key,
)

from .test_legislation_xml import XML


def _history_xml(version_date: str, sentence: str) -> bytes:
    data = XML.replace(b"2026-01-01", version_date.encode())
    data = data.replace(b"A person may be admitted to bail.", sentence.encode())
    return data


def _load(conn):
    current = parse_document(XML)
    upsert_document(conn, current, "current.xml", "current")
    for version_date, sentence in [
        ("2020-01-01", "The old bail rule applied."),
        ("2022-06-01", "The revised bail rule applied."),
    ]:
        doc = parse_document(_history_xml(version_date, sentence))
        upsert_history_document(conn, doc, f"{version_date}.xml", version_date)
    conn.commit()


def test_history_selects_version_in_force(conn):
    _load(conn)
    old = get_statute_history(conn, "999", "9", as_of="2021-01-01")
    assert old["found"] is True
    assert old["historical"] is True
    assert old["version_date"] == "2020-01-01"
    assert "old bail rule" in old["text"]
    assert old["next_version_date"] == "2022-06-01"
    assert "later_version_warning" in old


def test_history_selects_later_version(conn):
    _load(conn)
    new = get_statute_history(conn, "999", "9", as_of="2023-01-01")
    assert new["version_date"] == "2022-06-01"
    assert "revised bail rule" in new["text"]


def test_history_falls_back_to_current(conn):
    _load(conn)
    result = get_statute_history(conn, "999", "9", as_of="2019-01-01")
    assert result["found"] is True
    assert result["historical"] is False
    assert result["version_date"] == "2026-01-01"
    assert "do not treat it as the law in force" in result["warning"]


def test_history_today_returns_current(conn):
    _load(conn)
    result = get_statute_history(conn, "999", "9", as_of="2026-06-01")
    assert result["found"] is True
    assert result["historical"] is False
    assert result.get("current") is True
    assert result["version_date"] == "2026-01-01"
    assert "on or after the current version date" in result["warning"]


def test_list_section_versions(conn):
    _load(conn)
    result = list_section_versions(conn, "999", "9")
    assert result["count"] == 2
    assert [v["version_date"] for v in result["versions"]] == [
        "2020-01-01",
        "2022-06-01",
    ]


def test_section_range(conn):
    _load(conn)
    result = get_section_range(conn, "999", "1", "10")
    assert result["total_matched"] >= 2
    citations = {item["citation"] for item in result["results"]}
    assert "Cap. 999 s.1" in citations
    assert "Cap. 999 s.9" in citations


def test_section_sort_key_orders_suffixes():
    assert section_sort_key("9") < section_sort_key("9A") < section_sort_key("9J")
    assert section_sort_key("9J") < section_sort_key("10")
    assert section_sort_key("sch3") > section_sort_key("100")
