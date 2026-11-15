from hk_criminal_law_mcp.legislation_xml import parse_document

XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ordinance xmlns="http://www.xml.gov.hk/schemas/hklm/1.0"
           xmlns:dc="http://purl.org/dc/elements/1.1/" xml:lang="en">
  <meta>
    <docName>Cap. 999</docName>
    <docType>cap</docType>
    <docNumber>999</docNumber>
    <docStatus>In effect</docStatus>
    <dc:date>2026-01-01</dc:date>
    <dc:language>en</dc:language>
  </meta>
  <main>
    <longTitle>An Ordinance for testing.</longTitle>
    <section name="s1" temporalId="s1" status="operational" reason="inEffect">
      <num value="1">1.</num>
      <heading>Short title</heading>
      <content>This Ordinance may be cited as the <shortTitle>Test Ordinance</shortTitle>.</content>
    </section>
    <section name="s10" temporalId="s10" status="repealed" reason="repealed">
      <num value="10">10.</num>
      <sourceNote>(Repealed)</sourceNote>
    </section>
    <part name="P1">
      <num value="I">Part I</num>
      <heading>Bail</heading>
      <section name="s9" temporalId="s9" status="operational" reason="inEffect">
        <num value="9">9.</num>
        <heading>Bail</heading>
        <subsection name="1" temporalId="s9_1">
          <num value="1">(1)</num>
          <content>A person may be admitted to bail.</content>
        </subsection>
        <subsection name="2" temporalId="s9_2">
          <num value="2">(2)</num>
          <content>Bail conditions must be justified.</content>
        </subsection>
      </section>
    </part>
    <schedule name="sch1">
      <num value="1">Schedule 1</num>
      <heading>Offences</heading>
      <section name="s1" class="no_header">
        <num value="1">1.</num>
        <content>An offence in a schedule.</content>
      </section>
    </schedule>
  </main>
</ordinance>
"""


def test_parse_metadata_and_sections():
    doc = parse_document(XML)
    assert doc.cap == "999"
    assert doc.title == "Test Ordinance"
    assert doc.language == "en"
    assert doc.version_date == "2026-01-01"
    keys = {s.section_key for s in doc.sections}
    assert "s1" in keys
    assert "s9" in keys
    assert "sch1" in keys
    assert "s10" not in keys  # repealed
    s9 = next(s for s in doc.sections if s.section_key == "s9")
    assert s9.part == "Bail"
    assert "admitted to bail" in s9.text
    assert "conditions must be justified" in s9.text
    sch = next(s for s in doc.sections if s.section_key == "sch1")
    assert "Schedule 1" in sch.heading
    assert "An offence in a schedule" in sch.text
