import httpx

from hk_criminal_law_mcp.doj import (
    DojSeed,
    doj_status,
    get_doj_document,
    list_doj_documents,
    parse_doj_html,
    search_doj,
    store_doj_document,
    sync_doj,
    verify_doj_citation,
)

URL = "https://www.doj.gov.hk/en/publications/prosecution_ch5.html"
HTML = """<!DOCTYPE html>
<html><head>
<title>Department of Justice - Publications - Prosecution - Decision to Prosecute</title>
<meta name="last-modified" content="2020-09-01">
</head><body>
<!-- ************** content starts ************** -->
<p id="5"><i>5. Decision to Prosecute</i></p>
<p>5.9&nbsp;&nbsp;&nbsp;There can be no exhaustive list of the considerations to be
addressed when making this assessment, but they include:</p>
<ol class="lowerAlpha">
<li>the availability and efficacy of alternatives to prosecution, such as a
caution, warning or other acceptable form of diversion.</li>
</ol>
<!-- ************** content ends ************** -->
</body></html>"""


def _doc():
    return parse_doj_html(
        HTML,
        URL,
        slug="prosecution_ch5",
        category="prosecution_code",
        language="en",
        title="Prosecution Code — Chapter 5: Decision to Prosecute",
        last_modified="Mon, 14 Sep 2020 07:24:57 GMT",
    )


def test_parse_doj_html():
    document = _doc()
    assert document["title"].startswith("Prosecution Code")
    assert document["version_date"] == "2020-09-01"
    assert any(item["para_no"] == "5.9" for item in document["paragraphs"])
    assert "alternatives to prosecution" in document["text"]
    assert document["checksum"]


def test_store_search_and_get(conn):
    store_doj_document(conn, _doc())
    hit = search_doj(conn, "considerations")
    assert hit["count"] >= 1
    assert any(item["paragraph"] == "5.9" for item in hit["results"])
    alt = search_doj(conn, "alternatives to prosecution")
    assert alt["count"] >= 1
    assert any("alternatives" in (item["snippet"] or "") for item in alt["results"])

    document = get_doj_document(conn, "prosecution_ch5")
    assert document["found"] is True
    assert any(item["paragraph"] == "5.9" for item in document["paragraphs"])

    filtered = get_doj_document(conn, "prosecution_ch5", paragraphs=["5.9"])
    assert [item["paragraph"] for item in filtered["paragraphs"]] == ["5.9"]

    listed = list_doj_documents(conn)
    assert listed["count"] == 1
    assert listed["results"][0]["slug"] == "prosecution_ch5"

    status = doj_status(conn)
    assert status["documents"] == 1
    assert status["by_category"]["prosecution_code"] == 1

    verified = verify_doj_citation(conn, "Prosecution Code §5.9")
    assert verified["status"] == "verified"
    assert verified["matches"][0]["paragraph"] == "5.9"


def test_store_is_idempotent(conn):
    store_doj_document(conn, _doc())
    store_doj_document(conn, _doc())
    status = doj_status(conn)
    assert status["documents"] == 1
    assert status["paragraphs"] == len(_doc()["paragraphs"])


def test_sync_doj_with_mock_transport(conn):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("prosecution_ch5.html"):
            return httpx.Response(
                200,
                text=HTML,
                headers={"last-modified": "Mon, 14 Sep 2020 07:24:57 GMT"},
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    seeds = [
        DojSeed(
            "prosecution_ch5",
            "prosecution_code",
            "Prosecution Code — Chapter 5: Decision to Prosecute",
        )
    ]
    first = sync_doj(conn, client=client, seeds=seeds, request_interval=0)
    assert first["stats"]["documents_updated"] == 1
    second = sync_doj(conn, client=client, seeds=seeds, request_interval=0)
    assert second["stats"]["documents_unchanged"] == 1
    client.close()
    assert doj_status(conn)["documents"] == 1


def test_verify_doj_unrecognised(conn):
    result = verify_doj_citation(conn, "Cap. 212 s.40")
    assert result["status"] == "unrecognised"
