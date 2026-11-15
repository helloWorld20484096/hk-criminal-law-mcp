"""Parse Hong Kong e-Legislation (HKeL) XML into citable sections.

The HKeL bulk XML uses the HKL M 1.0 schema. This module deliberately keeps
only what a researcher needs: document metadata, section numbering, headings,
the operative text (without amendment source notes), and the part/division
context. It does not attempt to reproduce the official layout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

NS = {"h": "http://www.xml.gov.hk/schemas/hklm/1.0"}
Q = lambda name: f"{{{NS['h']}}}{name}"  # noqa: E731
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

_SKIP = {"sourceNote", "marker"}
_INDENT = {"subsection": "", "paragraph": "  ", "subparagraph": "    "}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _inline(el: etree._Element) -> str:
    """Collapse a fragment to a single line."""
    text = "".join(el.itertext())
    return re.sub(r"\s+", " ", text).strip()


def _txt(value: str | None) -> str:
    """Collapse whitespace inside an XML text node to a single space."""
    return re.sub(r"\s+", " ", value) if value else ""


def _mixed(el: etree._Element) -> str:
    parts: list[str] = [_txt(el.text)]
    for child in el:
        parts.append(_render(child))
        parts.append(_txt(child.tail))
    return "".join(parts)


def _render(el: etree._Element) -> str:
    tag = local(el.tag)
    if tag in _SKIP:
        return ""
    if tag == "num":
        return _inline(el) + " "
    if tag in {"heading", "crossHeading"}:
        return "\n" + _inline(el) + "\n"
    if tag in _INDENT:
        inner = _mixed(el).strip()
        if not inner:
            return ""
        return "\n" + _INDENT[tag] + inner
    if tag == "tr":
        cells = [_inline(c) for c in el if local(c.tag) in {"td", "th"}]
        return "\n" + " | ".join(cells)
    if tag == "def":
        return "\n" + _mixed(el).strip()
    if tag in {"table", "section", "schedule"}:
        return "\n" + _mixed(el) + "\n"
    return _mixed(el)


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = re.sub(r"[ \f\v]+", " ", text)
    lines = [re.sub(r" +", " ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line:
            out.append(line)
    return "\n".join(out).strip()


def render_fragment(el: etree._Element) -> str:
    """Render the operative text of a section/schedule fragment."""
    return _normalise(_render(el))


def _heading_of(el: etree._Element) -> str:
    h = el.find(Q("heading"))
    if h is not None:
        return _inline(h)
    n = el.find(Q("num"))
    return _inline(n) if n is not None else ""


def _ancestor_context(el: etree._Element) -> tuple[str | None, str | None]:
    part = division = None
    parent = el.getparent()
    while parent is not None:
        tag = local(parent.tag)
        if tag == "division" and division is None:
            division = _heading_of(parent)
        elif tag == "part" and part is None:
            part = _heading_of(parent)
        elif tag == "section" and parent.get("role") == "order" and part is None:
            num = parent.find(Q("num"))
            order_num = _inline(num) if num is not None else ""
            order_heading = _heading_of(parent)
            part = " — ".join(x for x in (order_num, order_heading) if x) or None
        parent = parent.getparent()
    return part, division


def _has_ancestor(el: etree._Element, tag_name: str) -> bool:
    parent = el.getparent()
    while parent is not None:
        if local(parent.tag) == tag_name:
            return True
        parent = parent.getparent()
    return False


@dataclass
class ParsedSection:
    section_key: str
    section_no: str
    heading: str
    text: str
    part: str | None = None
    division: str | None = None
    source_note: str | None = None


@dataclass
class ParsedDocument:
    cap: str
    doc_type: str
    doc_number: str
    doc_name: str
    title: str
    long_title: str
    language: str
    version_date: str
    status: str
    sections: list[ParsedSection] = field(default_factory=list)


def _normalise_language(raw: str) -> str:
    raw = (raw or "en").strip()
    if raw.lower().startswith("zh-hant"):
        return "zh-Hant"
    if raw.lower().startswith("zh-hans"):
        return "zh-Hans"
    if raw.lower().startswith("zh"):
        return "zh-Hant"
    return "en"


def _normalise_date(raw: str) -> str:
    """Keep the calendar date part of an ISO timestamp."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", raw or "")
    return match.group(1) if match else (raw or "")


def _meta_map(root: etree._Element) -> dict[str, str]:
    meta = root.find(Q("meta"))
    if meta is None:
        return {}
    out: dict[str, str] = {}
    for child in meta:
        tag = local(child.tag)
        out[tag] = (child.text or "").strip()
    return out


def parse_document(data: bytes, source_file: str = "") -> ParsedDocument:
    """Parse one HKeL XML document."""
    parser = etree.XMLParser(recover=True, resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser=parser)
    if root is None:
        raise ValueError(f"unparseable XML: {source_file}")

    meta = _meta_map(root)
    doc_number = meta.get("docNumber") or ""
    cap = re.sub(r"^Cap\.?\s*", "", doc_number, flags=re.I).strip() or doc_number
    doc_type = meta.get("docType") or "cap"
    doc_name = meta.get("docName") or f"Cap. {cap}"
    language = _normalise_language(meta.get("language") or root.get(XML_LANG) or "en")
    version_date = _normalise_date(meta.get("date") or "")
    status = meta.get("docStatus") or ""

    main = root.find(Q("main"))
    scope = main if main is not None else root

    long_title_el = scope.find(Q("longTitle"))
    long_title = _inline(long_title_el) if long_title_el is not None else ""

    short_title = ""
    for st in root.iter(Q("shortTitle")):
        short_title = _inline(st)
        if short_title:
            break
    if not short_title:
        # Constitutional instruments use <docTitle name="shortTitle">.
        for dt in root.iter(Q("docTitle")):
            short_title = _inline(dt)
            if short_title:
                break
    title = short_title or doc_name
    if not long_title:
        long_title = title

    sections: list[ParsedSection] = []
    for sec in scope.iter(Q("section")):
        if _has_ancestor(sec, "schedule"):
            continue
        role = (sec.get("role") or "").lower()
        if role == "order":
            # Container for the rules of a High Court Order; the rules are
            # indexed below with this Order recorded as their part context.
            continue
        if _has_ancestor(sec, "section") and role != "rule":
            continue
        if (sec.get("status") or "").lower() == "repealed" or (
            sec.get("reason") or ""
        ).lower() == "repealed":
            continue
        key = sec.get("temporalId") or sec.get("name") or ""
        num_el = sec.find(Q("num"))
        num = (num_el.get("value") if num_el is not None else "") or (num_el.text if num_el is not None else "")
        num = (num or key.lstrip("s")).strip()
        key = key or f"s{num}"
        heading = _heading_of(sec)
        body = render_fragment(sec)
        source_notes = [
            _inline(sn) for sn in sec.findall(Q("sourceNote")) if _inline(sn)
        ]
        part, division = _ancestor_context(sec)
        if not body and not heading:
            continue
        sections.append(
            ParsedSection(
                section_key=key,
                section_no=num,
                heading=heading,
                text=body,
                part=part,
                division=division,
                source_note="; ".join(source_notes) or None,
            )
        )

    for sch in scope.iter(Q("schedule")):
        if _has_ancestor(sch, "schedule"):
            continue
        if (sch.get("status") or "").lower() == "repealed" or (
            sch.get("reason") or ""
        ).lower() == "repealed":
            continue
        key = sch.get("name") or ""
        num_el = sch.find(Q("num"))
        num_text = _inline(num_el) if num_el is not None else ""
        num = (num_el.get("value") if num_el is not None else "") or num_text
        num = (num or key.replace("sch", "")).strip()
        key = key or f"sch{num}"
        heading = _heading_of(sch)
        if num_text and heading and heading != num_text:
            heading = f"{num_text} — {heading}"
        elif num_text:
            heading = num_text
        body = render_fragment(sch)
        source_notes = [
            _inline(sn) for sn in sch.findall(Q("sourceNote")) if _inline(sn)
        ]
        if not body and not heading:
            continue
        sections.append(
            ParsedSection(
                section_key=key,
                section_no=key,
                heading=heading,
                text=body,
                source_note="; ".join(source_notes) or None,
            )
        )

    # Instruments occasionally carry no <section>; keep the whole operative text.
    if not sections:
        body = render_fragment(scope)
        if body:
            sections.append(
                ParsedSection(
                    section_key="document",
                    section_no="document",
                    heading=title,
                    text=body,
                )
            )

    # A few documents reuse section names across Parts/Orders. Keep every
    # section but make its storage key unique.
    seen: dict[str, int] = {}
    for section in sections:
        base = section.section_key
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            section.section_key = f"{base}~{seen[base]}"

    return ParsedDocument(
        cap=cap,
        doc_type=doc_type,
        doc_number=doc_number or cap,
        doc_name=doc_name,
        title=title,
        long_title=long_title,
        language=language,
        version_date=version_date,
        status=status,
        sections=sections,
    )
