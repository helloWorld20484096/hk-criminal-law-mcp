from hk_criminal_law_mcp.hklii import (
    _parse_judgment_html,
    _parse_search_result,
    _result_court_key,
)

HTML = """
<html><head><title>FACC2/2020 HKSAR v. TEST</title></head><body>
<p>Before: Chief Justice</p>
<p><a class="para" id="p1" name="p1">1.</a> The appeal is allowed.</p>
<p><a class="para" id="p2" name="p2">2.</a> Bail conditions must be justified.</p>
</body></html>
"""


def test_parse_judgment_html():
    parsed = _parse_judgment_html(HTML)
    assert parsed["title"] == "FACC2/2020 HKSAR v. TEST"
    assert [p["number"] for p in parsed["paragraphs"]] == ["1", "2"]
    assert "appeal is allowed" in parsed["paragraphs"][0]["text"]
    assert "Bail conditions" in parsed["paragraphs"][1]["text"]
    assert "1. The appeal is allowed" in parsed["text"]


def test_parse_search_result():
    raw = {
        "title": "HKSAR V. TEST",
        "path": "/en/cases/hkcfa/2021/1",
        "db": "Court of Final Appeal",
        "pub_date": "2021-01-12T00:00:00+08:00",
    }
    parsed = _parse_search_result(raw)
    assert parsed is not None
    assert parsed["citation"] == "[2021] HKCFA 1"
    assert parsed["court_abbr"] == "hkcfa"
    assert parsed["language"] == "en"


def test_parse_chinese_search_result():
    raw = {"title": "香港特別行政區 訴 某人", "path": "/tc/cases/hkdc/2024/1154", "db": "區域法院"}
    parsed = _parse_search_result(raw)
    assert parsed is not None
    assert parsed["citation"] == "[2024] HKDC 1154"
    assert parsed["language"] == "zh-Hant"


def test_court_filter():
    assert _result_court_key("HKCFA") == "hkcfa"
    assert _result_court_key("Court of Final Appeal") == "hkcfa"
    assert _result_court_key("Court of Appeal") == "hkca"
    assert _result_court_key(None) is None
