"""Which loci a laboratory actually reports, and what an empty cell then means.

`HA-009`, decided by the human operator on 2026-09-03. These forms print a DPA1
and DPB1 row and leave the cell empty; 44 of ~25,000 anchored cells of those two
loci carry a value. Sending every one of the rest to a reviewer is ~24,000 items
nobody can act on, because the test was never performed.

The danger is the mirror image: declaring a locus untested when the laboratory
does report it would erase real values from the record. So the rule is narrow,
it is measured rather than assumed, and it can only ever reclassify a cell the
resolver already found empty.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kidneymatch.hla.testing_policy import (
    LocusTestingPolicy,
    LocusTestingUnavailable,
    load_testing_policy,
)

pytestmark = pytest.mark.task("OCR-001")

CONFIG = Path(__file__).resolve().parents[2] / "config/locus_testing_rates.json"


@pytest.fixture(scope="module")
def policy() -> LocusTestingPolicy:
    return load_testing_policy()


def write_policy(path: Path, families: dict) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema": "locus-testing-rates/v1",
                "max_resolve_rate": 0.01,
                "min_anchored": 200,
                "measured_utc": "2026-09-03T00:00:00+00:00",
                "families": families,
            }
        ),
        encoding="utf-8",
    )
    return path


def stats(anchored: int, resolved: int, not_tested: bool) -> dict:
    return {
        "anchored": anchored,
        "resolved": resolved,
        "empty": anchored - resolved,
        "resolve_rate": round(resolved / anchored, 5),
        "not_tested": not_tested,
    }


# --- what the committed measurement says ----------------------------------


def test_the_committed_policy_names_only_the_loci_that_never_resolve(policy) -> None:
    """DPA1 and DPB1, on every family. Anything else in this list would mean
    the rule had started erasing values the laboratory did report."""
    named = sorted({locus for _family, locus in policy.not_tested_pairs()})
    assert named == ["DPA1", "DPB1"]


def test_a_locus_the_laboratory_does_report_is_never_declared_untested(policy) -> None:
    """DQA1 resolves on 3.9-11.9% of anchored cells and C on 11.7-28.3%. Both
    are low, and both are real testing."""
    for family in ("FORM#0", "FORM#1", "FORM#3", ""):
        for locus in ("A", "B", "C", "DRB1", "DQA1", "DQB1"):
            assert not policy.is_not_tested(family, locus), (family, locus)


def test_the_policy_records_the_rate_that_justified_each_call(policy) -> None:
    """A reclassification with no provenance cannot be audited, and this one
    silently removes 24,663 cells from the review queue."""
    rate = policy.resolve_rate("FORM#1", "DPB1")
    assert rate is not None
    assert rate < 0.01
    assert policy.anchored("FORM#1", "DPB1") > 200


# --- the boundaries -------------------------------------------------------


def test_an_unmeasured_family_is_never_assumed_untested(tmp_path: Path) -> None:
    """A form nobody has measured gets the safe answer, which is review."""
    policy = load_testing_policy(
        write_policy(tmp_path / "p.json", {"FORM#1": {"DPB1": stats(9000, 10, True)}})
    )
    assert policy.is_not_tested("FORM#1", "DPB1") is True
    assert policy.is_not_tested("FORM#9", "DPB1") is False
    assert policy.is_not_tested("", "DPB1") is False


def test_a_small_sample_never_declares_a_locus_untested(tmp_path: Path) -> None:
    """Nine anchored cells that all came back empty say nothing about a
    laboratory's practice."""
    policy = load_testing_policy(
        write_policy(tmp_path / "p.json", {"FORM#1": {"DPB1": stats(9, 0, False)}})
    )
    assert policy.is_not_tested("FORM#1", "DPB1") is False


def test_the_stored_verdict_is_trusted_over_a_recomputed_one(tmp_path: Path) -> None:
    """The file is generated deliberately and reviewed. Recomputing the verdict
    at load time would let a threshold change alter published records without
    anyone regenerating and reading the diff."""
    policy = load_testing_policy(
        write_policy(tmp_path / "p.json", {"FORM#1": {"DPB1": stats(9000, 8000, False)}})
    )
    assert policy.is_not_tested("FORM#1", "DPB1") is False


def test_a_missing_policy_fails_loudly(tmp_path: Path) -> None:
    """Degrading to "nothing is untested" would silently restore 24,663 review
    items; degrading to "everything is" would erase values. Neither is a
    default anyone should get by accident."""
    with pytest.raises(LocusTestingUnavailable):
        load_testing_policy(tmp_path / "absent.json")


def test_a_policy_of_the_wrong_schema_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"schema": "something-else/v9", "families": {}}), encoding="utf-8")
    with pytest.raises(LocusTestingUnavailable, match="schema"):
        load_testing_policy(path)


def test_the_reason_names_the_measurement_it_rests_on(policy) -> None:
    """This reclassification takes 24,663 cells out of the review queue. The
    record has to say why, in numbers, or nobody can check it later."""
    reason = policy.reason("FORM#1", "DPB1")
    assert "DPB1" in reason
    assert "does not perform this test" in reason
    assert "%" in reason


def test_an_unmeasured_pair_says_so_rather_than_inventing_a_rate(policy) -> None:
    assert policy.reason("FORM#9", "DPB1") == "no measured testing rate for this family"
    assert policy.resolve_rate("FORM#9", "DPB1") is None
    assert policy.anchored("FORM#9", "DPB1") == 0


def test_an_unreadable_policy_file_is_fatal(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(LocusTestingUnavailable, match="readable JSON"):
        load_testing_policy(path)
