from hk_criminal_law_mcp.ingest_legislation import upsert_document
from hk_criminal_law_mcp.legislation_xml import parse_document
from hk_criminal_law_mcp.search import (
    get_section,
    search_legislation,
    verify_citation,
)

from .test_legislation_xml import XML


def _load(conn):
    doc = parse_document(XML)
    upsert_document(conn, doc, "fixture.xml", "checksum")
    conn.commit()


def test_search_legislation(conn):
    _load(conn)
    result = search_legislation(conn, "bail conditions")
    assert result["count"] >= 1
    assert any("Cap. 999" in item["citation"] for item in result["results"])


def test_get_section(conn):
    _load(conn)
    result = get_section(conn, "Cap. 999", "s9")
    assert result["found"] is True
    assert "admitted to bail" in result["text"]
    assert result["part"] == "Bail"


def test_get_missing_section(conn):
    _load(conn)
    result = get_section(conn, "999", "99")
    assert result["found"] is False
    assert result["cap_found"] is True


def test_verify_legislation_citation(conn):
    _load(conn)
    result = verify_citation(conn, "Cap. 999 s.9", live=False)
    assert result["status"] == "verified"
    assert result["type"] == "legislation"


def test_verify_unknown_case_offline(conn):
    result = verify_citation(conn, "[2021] HKCFA 1", live=False)
    assert result["status"] == "unverified"
    assert result["type"] == "case"
