from hk_criminal_law_mcp.ingest_legislation import upsert_document
from hk_criminal_law_mcp.legislation_xml import parse_document
from hk_criminal_law_mcp.research import (
    authority_ranking,
    doctrine_research,
    sentencing_research,
)

from .test_legislation_xml import XML


def _load(conn):
    data = XML.replace(
        b"Bail conditions must be justified.",
        b"A person convicted shall be liable to imprisonment for 5 years.",
    )
    doc = parse_document(data)
    upsert_document(conn, doc, "fixture.xml", "fixture")
    cur = conn.execute(
        """
        INSERT INTO cases
            (neutral_citation, court, court_code, year, num, title, language,
             text, paragraphs_json, cited_cases_json)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "[2021] HKCFA 1",
            "Court of Final Appeal",
            "hkcfa",
            2021,
            "1",
            "HKSAR v Test",
            "en",
            "The bail conditions and sentencing appeal were considered.",
            "[]",
            "[]",
        ),
    )
    case_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO cases_fts_en(rowid, case_id, neutral_citation, title, text) "
        "VALUES (?,?,?,?,?)",
        (
            case_id,
            case_id,
            "[2021] HKCFA 1",
            "HKSAR v Test",
            "The bail conditions and sentencing appeal were considered.",
        ),
    )
    conn.commit()


def test_doctrine_research_returns_legislation_and_ranked_case(conn):
    _load(conn)
    result = doctrine_research(conn, "bail", live_cases=False)
    assert result["legislation"]["count"] >= 1
    assert result["cases"]["count"] >= 1
    top = result["cases"]["results"][0]
    assert top["citation"] == "[2021] HKCFA 1"
    assert top["court_level"] == 5


def test_sentencing_research_extracts_penalty(conn):
    _load(conn)
    result = sentencing_research(conn, "999", "9")
    assert result["found"] is True
    assert any("imprisonment" in excerpt for excerpt in result["penalty_excerpts"])
    assert "Not a sentencing tariff" in result["warning"]


def test_authority_ranking(conn):
    _load(conn)
    result = authority_ranking(conn, "bail", live=False)
    assert result["count"] >= 1
    assert result["results"][0]["citation"] == "[2021] HKCFA 1"
    assert result["results"][0]["court_level"] == 5
