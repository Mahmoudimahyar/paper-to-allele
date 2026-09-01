\
from __future__ import annotations
import re
from kidneymatch.hla.models import HLALocus, ReportedHLAValue

_VALUE_RE = re.compile(r"^(?P<locus>[A-Z0-9]+)\*(?P<fields>\d{2}(?::\d{2,3}){0,3}[A-Z]?)$")


def normalize_reported_hla(locus: HLALocus, raw_value: str) -> ReportedHLAValue:
    """Syntactic normalization only. Reference validity belongs to the py-ard/IPD adapter."""
    text = raw_value.strip().upper().replace(" ", "")
    if text.startswith("*"):
        text = f"{locus.value}{text}"
    match = _VALUE_RE.fullmatch(text)
    if not match or match.group("locus") != locus.value:
        return ReportedHLAValue(locus, raw_value, None, False, True)
    fields = match.group("fields")
    return ReportedHLAValue(
        locus=locus,
        raw_value=raw_value,
        normalized_value=text,
        is_low_resolution=":" not in fields,
        requires_review=False,
    )
