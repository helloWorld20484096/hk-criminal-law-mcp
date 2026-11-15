"""Citation parsing and normalisation for Hong Kong legislation and cases."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Neutral-citation court codes -> HKLII database abbreviation.
COURT_CODES: dict[str, str] = {
    "HKCFA": "hkcfa",
    "HKCA": "hkca",
    "HKCFI": "hkcfi",
    "HKDC": "hkdc",
    "HKMC": "hkmagc",
    "HKMAGC": "hkmagc",
    "HKCT": "hkct",
    "HKFC": "hkfc",
    "HKFAMC": "hkfc",
    "HKLDt": "hkldt",
    "HKLD T": "hkldt",
    "HKSC": "hksct",
    "HKSCT": "hksct",
    "HKCRC": "hkcrc",
    "HKOAT": "hkoat",
    "HKLAT": "hklat",
    "HKLT": "hklat",
}

COURT_NAMES: dict[str, str] = {
    "hkcfa": "Court of Final Appeal",
    "hkca": "Court of Appeal",
    "hkcfi": "Court of First Instance",
    "hkdc": "District Court",
    "hkmagc": "Magistrates' Courts",
    "hkct": "Competition Tribunal",
    "hkfc": "Family Court",
    "hkldt": "Lands Tribunal",
    "hksct": "Small Claims Tribunal",
    "hkcrc": "Coroner's Court",
    "hkoat": "Obscene Articles Tribunal",
    "hklat": "Labour Tribunal",
}

_CASE_RE = re.compile(r"\[\s*(\d{4})\s*\]\s*([A-Za-z]+)\s*(\d+)\b")
_LEG_RE = re.compile(
    r"\bCap\.?\s*([0-9]+[A-Za-z]*)\s*(?:,?\s*(?:s\.?|sec\.?|section)\s*([0-9]+[A-Za-z]*)|,?\s*(sch\.?|schedule)\s*([0-9]+[A-Za-z]*))?",
    re.I,
)
_LEG_REVERSE_RE = re.compile(
    r"(?:s\.?|sec\.?|section)\s*([0-9]+[A-Za-z]*)\s+of\s+(?:the\s+)?Cap\.?\s*([0-9]+[A-Za-z]*)",
    re.I,
)


@dataclass(frozen=True)
class CaseCitation:
    year: int
    code: str
    number: str

    @property
    def court_abbr(self) -> str | None:
        return COURT_CODES.get(self.code.upper()) or COURT_CODES.get(self.code)

    @property
    def normalised(self) -> str:
        return f"[{self.year}] {self.code.upper()} {self.number}"


@dataclass(frozen=True)
class LegislationCitation:
    cap: str
    section: str | None = None
    schedule: str | None = None

    @property
    def normalised(self) -> str:
        base = f"Cap. {self.cap}"
        if self.schedule:
            return f"{base} Sch. {self.schedule}"
        if self.section:
            return f"{base} s.{self.section}"
        return base


def normalise_cap(value: str) -> str:
    value = re.sub(r"^\s*Cap\.?\s*", "", value, flags=re.I).strip()
    value = value.replace(" ", "")
    return value.upper()


def normalise_section(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^(?:s\.?|sec\.?|section)\s*", "", value, flags=re.I)
    value = re.sub(r"^(?:sch\.?|schedule)\s*", "sch", value, flags=re.I)
    return value.replace(" ", "")


def parse_case_citation(text: str) -> CaseCitation | None:
    m = _CASE_RE.search(text or "")
    if not m:
        return None
    return CaseCitation(year=int(m.group(1)), code=m.group(2), number=m.group(3))


def parse_legislation_citation(text: str) -> LegislationCitation | None:
    text = text or ""
    m = _LEG_REVERSE_RE.search(text)
    if m:
        return LegislationCitation(
            cap=normalise_cap(m.group(2)), section=normalise_section(m.group(1))
        )
    m = _LEG_RE.search(text)
    if not m:
        return None
    cap = normalise_cap(m.group(1))
    if m.group(4):
        return LegislationCitation(cap=cap, schedule=normalise_section(m.group(4)).lstrip("sch"))
    section = normalise_section(m.group(2)) if m.group(2) else None
    return LegislationCitation(cap=cap, section=section)
