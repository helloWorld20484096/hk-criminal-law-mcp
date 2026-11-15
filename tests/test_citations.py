from hk_criminal_law_mcp.citations import (
    normalise_cap,
    normalise_section,
    parse_case_citation,
    parse_legislation_citation,
)


def test_case_citation():
    cit = parse_case_citation("HKSAR v Lo [2021] HKCFA 1")
    assert cit is not None
    assert cit.year == 2021
    assert cit.normalised == "[2021] HKCFA 1"
    assert cit.court_abbr == "hkcfa"


def test_case_citation_district_court():
    cit = parse_case_citation("[2023] HKDC 488")
    assert cit is not None
    assert cit.court_abbr == "hkdc"


def test_legislation_citation():
    cit = parse_legislation_citation("Cap. 221 s.9J")
    assert cit is not None
    assert cit.cap == "221"
    assert cit.section == "9J"
    assert cit.normalised == "Cap. 221 s.9J"


def test_legislation_reverse_citation():
    cit = parse_legislation_citation("section 9J of Cap. 221")
    assert cit is not None
    assert cit.cap == "221"
    assert cit.section == "9J"


def test_schedule_citation():
    cit = parse_legislation_citation("Cap. 221 Sch. 3")
    assert cit is not None
    assert cit.cap == "221"
    assert cit.schedule == "3"


def test_normalise():
    assert normalise_cap("Cap. 221") == "221"
    assert normalise_section("s. 9J") == "9J"
