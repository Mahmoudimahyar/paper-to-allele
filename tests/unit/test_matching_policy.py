"""The policy loader refuses a policy it cannot rank under.

`MATCH-001`. Policy: `docs/clinical/MATCHING_POLICY_V2.md` sections 6.4 and 10.

Every coefficient in the ranking comes from a versioned file rather than from
the code, which is what lets a past ordering be reproduced and explained. That
only holds if a file which cannot support an ordering is refused at load rather
than absorbed: a missing key filled with a default, or a gate that quietly
contradicts the DR rule, would produce rankings that no version string
describes. So the loader raises, and these tests are the counterexamples it has
to raise on.

The fixtures below are edits of the real policy file, written to a temporary
path. Nothing here writes to `config/`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kidneymatch.matching.policy import load_policy

REAL = Path("config/matching_policy_ir_v2.json")


def _written(tmp_path: Path, mutate: Any) -> Path:
    """The real policy with one edit applied, written where the loader can read it."""
    data = json.loads(REAL.read_text(encoding="utf-8"))
    mutate(data)
    target = tmp_path / "policy.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


def test_the_real_policy_file_loads(tmp_path: Path) -> None:
    """The control. Every refusal below is an edit of this, so if the unedited
    file did not load the other tests would prove nothing about the edit."""
    policy = load_policy(_written(tmp_path, lambda data: None))
    assert policy.policy_id == "IR_KIDNEY_SCREEN_2.0"
    assert policy.is_adopted is False


@pytest.mark.parametrize(
    "path",
    [
        ("policy_id",),
        ("status",),
        ("tiebreaker",),
        ("sort_tuple",),
        ("buckets_in_order",),
        ("tiebreaker", "first_mismatch"),
        ("tiebreaker", "second_mismatch"),
        ("tiebreaker", "gate"),
        ("loci", "ranked"),
        ("reproducibility", "imgt_version"),
        ("reproducibility", "pyard_version"),
    ],
    ids=lambda path: "-".join(path),
)
def test_a_missing_key_is_refused_rather_than_defaulted(
    tmp_path: Path, path: tuple[str, ...]
) -> None:
    """A default would be a coefficient nobody chose and no version records.

    The name of the missing key is in the message, because a loader that only
    says "invalid policy" leaves an operator diffing a 128-line file by eye.
    """

    def drop(data: dict[str, Any]) -> None:
        node: Any = data
        for key in path[:-1]:
            node = node[key]
        del node[path[-1]]

    with pytest.raises(ValueError, match="missing") as raised:
        load_policy(_written(tmp_path, drop))
    assert ".".join(path).split(".")[-1] in str(raised.value)


def test_a_gate_that_attenuates_a_matched_drb1_is_refused(tmp_path: Path) -> None:
    """Section 6.4: the halving applies only when DRB1 is MISmatched.

    A file setting `other_when_DRB1_matched` below the full gate would halve the
    class I charges for exactly the pairs the DR gate is meant to reward, so the
    ranking would still run and would still be reproducible, and would encode
    the opposite of the policy it names. That is the failure a version string
    cannot catch, so the loader catches it.
    """

    def attenuate(data: dict[str, Any]) -> None:
        data["tiebreaker"]["gate"]["other_when_DRB1_matched"] = 5

    with pytest.raises(ValueError, match="must not attenuate"):
        load_policy(_written(tmp_path, attenuate))


def test_a_scored_locus_with_no_charge_is_refused(tmp_path: Path) -> None:
    """A locus listed as ranked but absent from `first_mismatch` would be scored
    at zero, which is a locus silently dropped from the tie-breaker rather than
    a locus deliberately given no weight. Deliberate zero weight is expressed by
    `zero_weight`, and a reader can see it there."""

    def unfund(data: dict[str, Any]) -> None:
        data["loci"]["ranked"] = [*data["loci"]["ranked"], "DPB1"]

    with pytest.raises(ValueError, match="DPB1"):
        load_policy(_written(tmp_path, unfund))


def test_the_loader_reads_the_file_rather_than_a_cached_default(tmp_path: Path) -> None:
    """`load_policy` is memoised, so a second policy must not return the first.

    The cache is keyed on the path. A cache that ignored the argument would make
    every test above pass by accident, and would make a real second policy
    invisible to a caller that asked for it by name.
    """
    edited = _written(tmp_path, lambda data: data.__setitem__("policy_id", "OTHER_1.0"))
    assert load_policy(edited).policy_id == "OTHER_1.0"
    assert load_policy().policy_id == "IR_KIDNEY_SCREEN_2.0"
