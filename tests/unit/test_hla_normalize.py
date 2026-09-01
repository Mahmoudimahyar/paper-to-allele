from kidneymatch.hla.models import HLALocus
from kidneymatch.hla.normalize import normalize_reported_hla


def test_cell_locus_can_prefix_star_only_value() -> None:
    value = normalize_reported_hla(HLALocus.DQB1, "*06")
    assert value.normalized_value == "DQB1*06"
    assert value.is_low_resolution is True


def test_wrong_locus_is_not_silently_reassigned() -> None:
    value = normalize_reported_hla(HLALocus.B, "DQB1*06")
    assert value.normalized_value is None
    assert value.requires_review is True


def test_low_resolution_is_not_upgraded() -> None:
    value = normalize_reported_hla(HLALocus.A, "A*02")
    assert value.normalized_value == "A*02"
    assert value.normalized_value != "A*02:01"
