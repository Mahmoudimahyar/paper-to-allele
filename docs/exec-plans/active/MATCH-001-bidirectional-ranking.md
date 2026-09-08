# MATCH-001 — Bidirectional pre-screen ranking

**Status:** PLANNED (not started; the HLA weights are blocked by HA-004)
**Feature spec:** `specs/features/MATCH-001-ranking.json` (v2.0.0)
**Policy:** `docs/clinical/MATCHING_POLICY_V2.md` · `config/matching_policy_ir_v2.json`
**Evidence:** `docs/clinical/HLA_MATCHING_EVIDENCE_V2_2026-09-08.md`
**Phase:** V1-MATCH

## Objective

Rank all eligible donors for a given recipient, and all eligible recipients for
a given donor, deterministically, with an explanation that reconstructs the sort
key exactly. The algorithm is the UK Kidney Allocation Scheme mismatch levels,
re-cut on the HLA-DR gate and extended with HLA-DQ, per the policy.

## Non-goals

- Allocation, clearance, or any compatibility finding.
- A compatibility percentage.
- Molecular mismatch (eplet, PIRCHE-II, electrostatic, amino acid) from
  one-field typing.
- A matchability or waiting-time term in the ranking.
- Contacting anyone. Introductions are V4-BOT-MATCH.

## What is already built

- `src/kidneymatch/matching/abo.py` — the ABO gate, with the provenance
  asymmetry (a patient-reported group may exclude a pair but never clear one).
  Tested. Not yet wired into the core.
- `src/kidneymatch/matching/models.py` — `PairStage`, `MatchResult` skeleton.
- `src/kidneymatch/matching/core.py` — a placeholder that raises
  `MatchingNotImplemented`.
- `config/locus_genotype_frequencies.json` — measured chance-match rates per
  locus, used to justify treating DQ as binary.

## Invariants this plan must not break

- Gates precede the HLA heuristic, structurally: the bucket is tuple position 0.
- `UNKNOWN` is never 0, never contributes to a total, never improves a rank.
- One allele read is never homozygous; a partial locus yields a range.
- The count is host-versus-graft, with the recipient in the recipient argument
  in both directions. A pair result is cached, if at all, under the **ordered**
  pair.
- The matching package may not import compensation. Enforced by
  `scripts/architecture_lint.py`.
- Determinism: same snapshots plus same policy version give a byte-identical
  ordering. The clock is an injected argument.
- No user-facing percentage. A blocked pair is never rendered as a low rank.

## Milestones

- [ ] **M1. Mismatch vector** (`MATCH-HLA-001`). Implement the function of
      policy section 3: set semantics over distinct alleles at the compared
      depth; homozygosity falls out; `UNREAD` yields a range; `UNKNOWN` when
      either side lacks the locus; derive the allele count from the value and
      raise `REVIEW_REQUIRED` when it disagrees with the `second_allele` flag.
      Port `scratchpad/ref_mismatch.py`'s 13 worked cases as the first tests.
- [ ] **M2. Snapshot and run records** (`MATCH-DOMAIN-001`). Write-once
      `MatchSnapshot` with evidence blocks copied, not referenced; `MatchRun`
      recording policy version, IPD-IMGT/HLA 3.62, py-ard 1.5.5, gold build id,
      input typing resolution and `as_of`. The snapshot type has **no field**
      for compensation, identifiers, message text or preference claims.
- [ ] **M3. Gates as buckets** (`MATCH-ABO-001`, `MATCH-IMMUNE-001`). Wire the
      existing ABO gate in; implement the two-pass bucket assignment (blocking
      pass before informational pass) of policy section 5; DSA and crossmatch
      gates specified and inert, with `ANTIBODY_UNKNOWN` always displayed.
- [ ] **M4. KM levels and the sort tuple** (`MATCH-001`). Levels per policy
      section 6.2; the eight-position tuple; the integer tie-breaker with the DR
      gate. Port `scratchpad/ref_rank.py`'s worked example as a golden test.
- [ ] **M5. Both directions.** `rank_donors_for(recipient)` and
      `rank_recipients_for(donor)` over one mismatch function. Assert the
      asymmetry with a concrete pair.
- [ ] **M6. Explanation** (`MATCH-EXPLAIN-001`). Generated **from** the sort
      key so it cannot drift; carries per-locus status with reasons, structural
      notes (homozygosity, blood-group pool size, duplicate-candidate flag),
      missing data, blockers, next action and versions.
- [ ] **M7. Test suite** (`MATCH-EVAL-001`). Below.
- [ ] **M8. Clinician-review packet.** Below.

## Test design

Every invariant test is a checker that takes a ranking callable, and a meta-test
proves each checker **fails** against a deliberately broken ranker. The
repository has been burned by tests that could not fail; that is the guard.

Adversarial cases that must be present:

1. A barely typed donor must not outrank a fully typed, well-matched donor.
2. A homozygous donor into a heterozygous recipient counts 1, not 2.
3. `second_allele = UNREAD` yields a range, never a zero.
4. A row whose flag and value disagree raises `REVIEW_REQUIRED`.
5. ABO `UNKNOWN` never reaches a `RANKED` bucket.
6. A patient-reported ABO can exclude but never clear.
7. A positive crossmatch hard-stops a pair with a perfect HLA match.
8. A pair that is both `INSUFFICIENT_HLA` and blocked shows as blocked.
9. Changing any compensation field yields a byte-identical ordering.
10. `score(D→R) != score(R→D)` for a named homozygous pair.
11. A role-UNKNOWN profile appears in neither direction.
12. Deleting any locus typing, DRB3/4/5 included, never improves a rank.
13. Two profiles sharing a genotype tie, and the stable hash breaks it
      identically across runs and across input permutations.
14. A donor with 2 B and 0 DR outranks a donor with 0 B and 1 DR.

Property tests: the ordering is a total order; determinism under input
permutation (the Gold build had a real bug of this class); no float anywhere in
the sort key.

Fixtures are synthetic. **No real patient data in fixtures**, per AGENTS.md.

## Clinician-review packet (HA-004)

One page per question M1–M11 from policy section 10. Each page carries: the
question in one sentence; what the design currently does; the evidence behind it
with its effect size and source; the counter-evidence; and a yes/no/other box.
Accompanied by the worked example of policy section 6.5 rendered as the
administrator would see it, and by five real anonymised mismatch vectors drawn
from the archive with all identifiers removed, so the immunologist is ruling on
concrete cases rather than on prose.

## Risks

- The weights are transported from non-Iranian registries and cannot be
  calibrated until Iranian outcome data exists. The output says so.
- The archive has no antibody data, so the immunological gate that matters most
  clinically is inert. Every pair is `ANTIBODY_UNKNOWN` and this must stay
  visible rather than becoming background noise.
- 1,974 profiles share a genotype, so a result page may show one person twice.
- 49 Gold rows have a flag/value disagreement (tracked separately); M1's
  `REVIEW_REQUIRED` rule contains the damage but does not repair it.
