# Matching Policy V2 — `IR_KIDNEY_SCREEN_2.0`

**Supersedes:** `MATCHING_POLICY_V1.md` (`IR-KIDNEY-MATCH-1.0.0`)
**Date:** 2026-09-08
**Status:** DESIGN. The *structure* below is decided and implementable. The
clinical *weights* are a proposal blocked by HA-004. Nothing here changes
behaviour until the work-queue tasks are taken and the spec is frozen.
**Evidence base:** `HLA_MATCHING_EVIDENCE_V2_2026-09-08.md` (100 papers, 1,134
effect sizes), its methods and its appendix.

---

## 1. What this policy is, and is not

It ranks candidates for **further clinical evaluation**. It is a pre-screen. It
is not an allocation decision, not a compatibility finding, and not clearance
for transplant. The constitution permits the product to say it "ranks candidates
for further clinical evaluation according to a versioned pre-screening policy",
and forbids any claim that a pair is transplant-compatible.

Two directions are supported, because the operator requires both:

- `rank(donors | recipient)` — the roadmap's V1-MATCH goal.
- `rank(recipients | donor)` — an extension of the roadmap, added here.

These are **not** transposes of one another. Section 4 proves it.

### What V1 got wrong

V1 charged a constant penalty per mismatch at each locus and added a small
zero-mismatch bonus. The evidence review showed the antigen-level penalty is a
step rather than a ramp, that a second mismatch at a locus costs roughly a third
of the first, and that HLA-DR gates the value of matching the other loci. V1's
shape is therefore replaced, not merely re-tuned. V1's hard gates, its
compensation isolation and its refusal to display a percentage all stand.

---

## 2. What the archive can actually support

Measured from `data/gold/gold.sqlite` on 2026-09-08. Counts only.

| | Profiles |
|---|---|
| Gold profiles | 19,200 |
| …with at least one HLA value | 14,864 |
| A, B, DRB1 all **present** | 9,817 |
| A, B, DRB1 all **fully typed** (both alleles read) | **9,143** |
| …DONOR / RECIPIENT / role UNKNOWN | 5,288 / 2,866 / 989 |
| A, B, C, DRB1, DQB1 all fully typed | 2,432 |
| At least one partially typed locus | 2,695 |
| ABO known | 8,792 |
| Antibody, panel-reactive antibody, crossmatch | none |

Per-locus capture of the **second** allele:

| Locus | Typed | Both alleles | One allele only |
|---|---|---|---|
| A | 12,131 | 11,529 | 602 |
| B | 11,602 | 11,038 | 564 |
| C | 3,794 | 3,488 | 306 |
| DRB1 | 12,258 | 11,393 | 865 |
| DQB1 | 12,234 | 11,003 | 1,231 |
| DQA1 | 776 | 719 | 57 |

**The rankable pool.** Requiring a stated role, a known blood group and A+B+DRB1
fully typed on both sides: **3,051 donors** and **1,665 recipients**, giving
**2,820,846** ordered pairs that clear the ABO gate. That is small enough to
score on demand; no precomputed all-pairs matrix is needed or wanted, because a
stored matrix goes stale the moment a profile is re-reviewed.

**A profile is a photograph, not a person.** Deduplication ran at the image
level, and 1,974 profiles share a genotype with at least one other profile, so
the counts above are upper bounds on distinct people. `DEDUPE-001` forbids
merging on HLA similarity alone, which is why those profiles stay separate. Two
consequences for ranking: a result page may contain two entries that are the
same person, and the explanation must therefore carry the duplicate-candidate
flag the Gold build already records, so an administrator is not misled into
counting one donor twice.

**The blood-group floor.** Before HLA is considered at all, a recipient's pool
is set by ABO:

| Recipient group | Recipients | ABO-compatible donors |
|---|---|---|
| O | 571 | 1,032 |
| A | 590 | 2,080 |
| B | 401 | 1,721 |
| AB | 103 | 3,051 |

A group-O recipient sees a third of what an AB recipient sees. The explanation
must show this, or a short list will be misread as a poor HLA result.

**Three consequences bind the design.** No molecular method (eplet, PIRCHE-II,
electrostatic, amino-acid) can run, because every one needs two-field typing and
the constitution forbids imputing it for clinical output. HLA-C is unknown for
four profiles in five, so it must sort as unknown and never as zero. And every
pair is `ANTIBODY_UNKNOWN`, which matters because the evidence shows
sensitisation is what turns a minor locus into a major one.

---

## 3. The mismatch function

This is the foundation. An error here is clinically meaningful, so the rule is
stated exactly.

### 3.1 Direction

Kidney transplantation cares about **host versus graft**: the antigens the
recipient's immune system will see as foreign on the graft. So:

```
MM(locus) = | alleles(donor, locus) \ alleles(recipient, locus) |
```

the number of the **donor's distinct** alleles that the **recipient does not
have**. The reverse direction (recipient antigens absent from the donor) is
graft-versus-host, which is a haematopoietic-transplant concern and is never
what a kidney pre-screen counts.

**Provenance of this rule.** The direction and the distinct-allele convention
are standard histocompatibility practice and were already project policy
(`MATCHING_POLICY_V1` section 4). They are **not** findings of the evidence
review: that review extracted effect sizes, dose-response series and
interactions, and did not record any included paper's counting convention for a
homozygous donor. The rule is therefore adopted as established practice, and it
is listed for HA-004 confirmation (M11) rather than presented as measured.

Both ranking directions call one function with the recipient always in the
recipient argument. The arguments are never swapped to serve the other
direction; only the iteration changes.

### 3.2 Homozygosity falls out of set semantics

Because the count is over **distinct** donor alleles, homozygosity needs no
special case: a donor whose two alleles are equal contributes at most one
mismatch. Worked examples, all verified against a reference implementation:

| Donor | Recipient | Mismatches |
|---|---|---|
| A\*02, A\*11 | A\*01, A\*03 | 2 |
| A\*02, A\*11 | A\*02, A\*03 | 1 |
| A\*02, A\*11 | A\*02, A\*11 | 0 |
| A\*02, A\*02 (homozygous) | A\*02, A\*03 | 0 |
| A\*02, A\*02 (homozygous) | A\*01, A\*03 | **1** |
| A\*02, A\*11 | A\*02, A\*02 (homozygous recipient) | 1 |
| A\*02, A\*02 | A\*02, A\*02 | 0 |

Zygosity is a property of the **comparison**, not of a profile, because it
depends on the compared field depth. It must never be cached on a profile
record.

### 3.3 One allele read is not homozygosity

The archive stores `second_allele` as a status flag, `READ` or `UNREAD`, not as
a value. It exists because of KI-015: a single printed value does **not** mean
homozygous, it means one allele was read. Between 29% and 36% of resolved
A/B/DRB1 cells were single-valued, far above any plausible homozygosity rate.

The matching layer inherits that refusal. When either side has only one allele
read at a locus, the mismatch count is a **range**, not a number:

| Situation | Result |
|---|---|
| Donor one-typed, read allele shared with recipient | 0–1 |
| Donor one-typed, read allele foreign | 1–2 |
| Recipient one-typed, donor fully typed, nothing shared | 1–2 |
| Both one-typed, read alleles equal | 0–1 |

The known part is still counted, so a partial locus is not thrown away; but it
can never masquerade as a clean zero. **Where a range decides a level or a
comparison, the worse end is used** and the range is shown in the explanation.
Flattering a pair beyond what the data supports is the one direction of error
this system must not make.

**Trust the value, not the flag.** 49 rows currently carry `READ` while storing
one allele. The implementation derives the allele count from the value itself
and raises `REVIEW_REQUIRED` when the flag and the value disagree, rather than
trusting either. (Repair tracked separately.)

### 3.4 Resolution

Comparison happens at the depth actually stored, which is one field for 97% of
values. Two values match only if they are equal at the compared depth. Nothing
is ever expanded. When one side is two-field and the other one-field, both are
truncated to the coarser depth and the explanation records
`comparison_truncated: true`, because a one-field agreement is weaker evidence
than a two-field one and the reader must be able to see which happened.

### 3.5 UNKNOWN

If either side lacks the locus, the result is `UNKNOWN`. `UNKNOWN` is never 0
and never improves a rank. A pair missing DRB1 or B on either side does not
receive a level at all; it goes to the `INSUFFICIENT_HLA` bucket (section 5).

An earlier draft of this paragraph also said `UNKNOWN` "never contributes to a
total". That was true of the mismatch vector and false of the ranking, and the
ambiguity mattered enough to be worth separating here. `UNKNOWN` carries no
NUMBER: `count`, `lower` and `upper` are all absent, so it can never be summed
as a mismatch count and `count or 0` cannot turn it into a match. But it does
carry a CHARGE: section 6.4 prices it at its worst case in the tie-breaker,
precisely so that absence is never cheaper than a measured mismatch. Those two
statements are the same rule seen from two sides. A locus with no number that
also cost nothing would make deleting a bad typing an improvement, which is the
bug section 6.4 records.

### 3.6 The other loci

- **HLA-C** is compared when typed on both sides (20% of profiles) and is
  otherwise `UNKNOWN`. It never enters the level; it enters only the
  tie-breaker, at low weight, and only when known. Its evidence is confined to
  presensitised recipients, and this archive has no antibody data.
- **DRB3/4/5** are compared at **presence level only** per gene
  (`PRESENT`/`ABSENT`/`UNKNOWN`). A null-suffixed allele (`N`, not expressed)
  never feeds matching; it stays `REVIEW_REQUIRED` until HA-004, per
  `HLA_VALIDATION_SPEC` section 7.
- **DQA1/DQB1**: a heterodimer comparison is permitted **only** when both chains
  are two-field on both sides and phase is unambiguous. That is 776 profiles at
  best, so in practice DQB1 alone is compared and the output says so. Never
  claim complete HLA-DQ typing from DQB1 alone.
- **DPA1/DPB1** (26 and 34 profiles) carry no weight. They exist for the
  antibody gate when antibody data eventually arrives.

### 3.7 The mismatch vector

The unit passed to the ranking is:

```
MismatchVector = {
  per_locus: { A|B|C|DRB1|DQB1: { status: KNOWN|RANGE|UNKNOWN,
                                  count: int|null, lower: int|null, upper: int|null,
                                  compared_depth: "one_field"|"two_field",
                                  truncated: bool } },
  drbx: { DRB3|DRB4|DRB5: PRESENT|ABSENT|UNKNOWN|REVIEW_REQUIRED },
  dq_mode: "DQB1_ONLY" | "HETERODIMER",
  unknown_loci: [...],
  partial_loci: [...],
}
```

---

## 4. Both directions, and why they differ

### 4.1 The asymmetry

At a locus, with `d` and `r` the numbers of **distinct** alleles on each side:

```
MM(D→R) − MM(R→D) = d − r
```

so the two directions agree only when both sides have the same number of
distinct alleles at that locus. A homozygous side breaks it. Concretely:

> Donor homozygous A\*02/A\*02 into recipient A\*01/A\*03 → **1** mismatch.
> The same two people with roles swapped → **2** mismatches.

A homozygous person is therefore structurally advantaged as a **donor** and
structurally disadvantaged as a **recipient**. That is what the biology means,
not a scoring artefact, and the explanation must say so rather than let an
administrator read it as a data problem.

Zero mismatch in one direction is a **subset** relation, not identity. Zero in
both directions is identity.

### 4.2 What this means operationally

`rank(recipients | donor)` uses the **same** host-versus-graft direction,
holding the donor fixed and iterating over recipients. The transposed count is
never used for either query. One function, two iterations.

A pair's score is therefore stored, if stored at all, as a **directed** value
keyed by (donor_id, recipient_id). It must not be cached under an unordered pair
key. Scoring is on demand.

### 4.3 Role-UNKNOWN profiles

2,026 profiles have no established role, of which 989 are fully typed at
A+B+DRB1. They are **excluded from both directions** and reported in a separate
`EXCLUDED_NON_CLINICAL` bucket with the reason `role_unknown`. They are never
silently treated as either party. Establishing a role is a review action, not an
inference the matcher may make.

---

## 5. Stage one: the gates, as buckets

Every candidate lands in exactly one bucket. Buckets are rendered as separate
sections with their own next action. A blocked pair is **not** a low-ranked
pair, and must never appear at the bottom of a ranked list where someone could
act on it.

| Display order | Bucket | Entry condition | Next action |
|---|---|---|---|
| 0 | `RANKED` | all gates clear; both blood groups laboratory-measured; DRB1 and B known both sides | proceed to clinical evaluation |
| 1 | `PROVISIONAL_ABO` | as `RANKED`, but a blood group is patient-reported or a caption claim | obtain a laboratory blood group |
| 2 | `INSUFFICIENT_HLA` | gates clear, but DRB1 or B unknown on either side | obtain HLA typing |
| 3 | `INSUFFICIENT_ABO` | blood group absent, or present but not an ABO letter, on either side | obtain a laboratory blood group |
| 4 | `ABO_INCOMPATIBLE` | letters incompatible donor→recipient | not a candidate |
| 5 | `BLOCKED_DSA_OR_LAB_REVIEW` | reviewed unacceptable antigen or DSA targets a reviewed donor value | laboratory review |
| 6 | `BLOCKED_POSITIVE_CROSSMATCH` | valid current positive physical crossmatch | direct pathway blocked |
| 7 | `EXCLUDED_NON_CLINICAL` | role unknown, consent, quarantine, withdrawal | none |

**Assignment precedence is not the display order.** A pair can satisfy more than
one entry condition, and taking the first match in display order would let an
informational bucket hide a blocking one: a pair that is both `INSUFFICIENT_HLA`
and `BLOCKED_POSITIVE_CROSSMATCH` would be shown as merely under-typed. So
assignment runs in two passes:

1. **Blocking pass**, evaluated first, in this order: `EXCLUDED_NON_CLINICAL`,
   `BLOCKED_POSITIVE_CROSSMATCH`, `BLOCKED_DSA_OR_LAB_REVIEW`,
   `ABO_INCOMPATIBLE`. The first condition that holds wins and assignment stops.
2. **Informational pass**, only if no blocking condition held:
   `INSUFFICIENT_ABO`, `INSUFFICIENT_HLA`, `PROVISIONAL_ABO`, `RANKED`.

**An unreadable blood group is a missing one, not a weak one.** `PROVISIONAL_ABO`
is a *ranked* bucket: it says the letters are known and compatible and only the
provenance is short of a laboratory measurement. A cell that holds something
which is not an ABO letter at all - an OCR garble, an Rh-carrying string such as
`O+`, a stray value from a neighbouring column - carries no letters to be
compatible about, so it fails the readability check before provenance is
consulted and lands in `INSUFFICIENT_ABO`. Routing it on provenance instead
would put an unreadable group into a ranked list, which is the one place it must
never reach. Provenance is only asked about a value that has already been read.

Every blocking reason that applied is additionally listed in the explanation's
`blockers` array, so a pair blocked for two reasons reports both even though it
occupies one bucket. Display order then governs only how the buckets are
rendered on the page.

**ABO** is already implemented (`src/kidneymatch/matching/abo.py`, MATCH-ABO-001)
and this policy does not change it. Its central asymmetry stands: a
patient-reported group may **exclude** a pair but may never **clear** one,
because a wrong exclusion costs a missed match while a wrong clearance costs an
incompatible transplant. Measured basis: the dominant letterhead disclaims
responsibility for the blood group on 2,928 documents (KI-014).

**DSA and crossmatch** gates are specified but currently inert: the archive has
no antibody or crossmatch data at all. Every pair is therefore
`ANTIBODY_UNKNOWN`, and that status is displayed prominently rather than
silently omitted. Absence of antibody data is not evidence of absence of
antibody.

---

## 6. Stage two: the ranking

### 6.1 Which published algorithm this is

The base is the **UK Kidney Allocation Scheme mismatch levels**, which group
pairs into four ordered tiers from HLA-DR and HLA-B rather than summing a count.
A level scheme is the right family because the evidence says the antigen-level
relationship is a step, not a ramp: in the cleanest test, non-zero groups did
not differ from one another at all (p = 0.48).

The UK levels are:

| UK level | Definition |
|---|---|
| 1 | 0 A, 0 B, 0 DR |
| 2 | (0 DR and 0–1 B) or (1 DR and 0 B), excluding level 1 |
| 3 | (0 DR and 2 B) or (1 DR and 1 B) or (2 DR and 0 B) |
| 4 | everything else |

Measured against outcome in 25,094 UK transplants, level 2 was **not** worse
than level 1 (sub-hazard ratio 0.973, 0.863–1.097), while levels 3 and 4 were
(1.132 and 1.190).

**Three evidence-driven modifications** turn this into the KM levels.

**One, the DR gate.** UK level 2 admits a pair with one DR mismatch and no B
mismatch, ranking it above a pair with zero DR and two B. That contradicts the
strongest interaction finding in the review: in 39,205 Eurotransplant
transplants, "the introduction of a single HLA-DR incompatibility eliminates the
HLA-A,B matching effect." The levels are therefore re-cut so that **every
DR-matched pair outranks every DR-mismatched pair.**

**Two, B splits at 2, not at 1.** In the UK per-locus analysis two B mismatches
reached significance for graft failure (1.146, 1.002–1.310) while one did not
(1.082, 0.969–1.209). So 0 and 1 B mismatches are merged within a DR tier.

**Three, DQ enters below the level, as a binary.** The UK scheme has no DQ; this
archive has DQB1 on 12,234 profiles, so it must be used. It is binary (zero
versus anything else) for three measured reasons: no separation among non-zero
groups at antigen level (p = 0.48); the one-field DQ call is the least reliable
of the five loci, with low-resolution typing disproving donor specificity in
22.8% of suspected cases and imputation agreeing with two-field genotypes only
35.4% of the time at class II; and in this archive DQB1 has only 30 distinct
genotypes with a chance-match probability of 0.101 against DRB1's 0.023
(`config/locus_genotype_frequencies.json`, measured 2026-09-03), so a one-field
DQ zero-mismatch arises by chance about **4.5 times** more often than a DRB1 one
and carries correspondingly less information.

Taken from OPTN: treating the zero category as a *classification* rather than as
points. Taken from São Paulo: the locus ordering DR ≫ B > A, which anchors the
tie-breaker magnitudes; its within-locus linearity is rejected and replaced by
the measured concavity. **Not adopted:** any additive score over the total
mismatch count.

### 6.2 The KM levels

| Level | DRB1 | HLA-B | HLA-A | Meaning |
|---|---|---|---|---|
| KM-1 | 0 | 0 | 0 | full match on the classic three |
| KM-2 | 0 | ≤1 | any | DR and B favourable |
| KM-3 | 0 | 2 | any | DR matched, B fully mismatched |
| KM-4 | 1 | ≤1 | any | one DR mismatch |
| KM-5 | 1 | 2 | any | |
| KM-6 | 2 | ≤1 | any | both DR mismatched |
| KM-7 | 2 | 2 | any | |

HLA-A distinguishes only KM-1 from KM-2, matching its evidence: no independent
graft-survival signal, point estimates below 1.0 in the UK registry, and no
locus-specific effect in the largest permutation analysis.

A pair whose DR or B count is a **range** takes the level implied by the worse
end, and the explanation shows the range and the level it would have reached at
the better end.

**KM-1 requires HLA-A to be known and matched on both sides.** An unknown A
cannot satisfy `A = 0`, so a pair with DR 0, B 0 and A unknown falls to KM-2.
This is intended, not an accident of the ordering: KM-1 is the claim that the
classic three loci are fully matched, and that claim cannot be made from missing
data. The explanation states `km_1_unreachable: "HLA-A unknown"` so the reader
can see why an otherwise perfect pair sits at KM-2. Unknown DR or B does not
produce a level at all; the pair goes to `INSUFFICIENT_HLA`.

### 6.3 The sort tuple

Ranking is lexicographic. Position 0 is the bucket, so gates always precede the
HLA heuristic, structurally rather than by convention.

| # | Key | Ascending order |
|---|---|---|
| 0 | bucket | `RANKED` < `PROVISIONAL_ABO` < … (section 5) |
| 1 | KM level | 1 … 7 |
| 2 | DQB1 mismatch, binary | 0 < (≥1 or UNKNOWN) |
| 3 | numeric tie-breaker | ascending (section 6.4) |
| 4 | evidence quality penalty | fewer tier-C / review fields first |
| 5 | count of UNKNOWN required loci | fewer first |
| 6 | count of partially typed loci | fewer first |
| 7 | stable identifier hash | deterministic, never price or anything correlated with it |

Position 2 places DQ **below** the level and above the tie-breaker: DQ separates
candidates once the level is fixed. Positions 5 and 6 are what stop a
poorly typed profile from winning by having fewer countable mismatches: a
candidate with unknown loci sorts after an otherwise equal candidate that is
fully typed.

**Positions 5 and 6 prefer the better-typed candidate among equals**, but they
cannot be what enforces the monotonicity invariant. An earlier draft of this
section claimed that counting a now-unknown locus at position 5 offsets the
tie-breaker charge that vanished when its typing was deleted. That is
arithmetically impossible in a lexicographic key: position 3 is compared and
decided before position 5 is ever read, so no later position can offset an
earlier one. The claim was wrong and the implementation that followed it let
deleting a mismatched typing improve a candidate's rank. Property-based tests
caught it. The invariant is enforced in the tie-breaker itself instead (§6.4).

### 6.4 The numeric tie-breaker

Admin-only, never displayed as a percentage, never displayed to end users.
Integer arithmetic in tenths so the DR gate's halving stays exact and the
ordering is reproducible bit for bit.

```
penalty = Σ_locus  gate(locus) × [ first(locus) × 1(mm ≥ 1)
                                 + second(locus) × 1(mm = 2) ]

gate(DRB1) = 10                                  (tenths; 10 = ×1.0)
gate(other) = 10 if DRB1 mismatch = 0 else 5     (×0.5 once DR is lost)
```

| Locus | First mismatch | Second mismatch | Second ÷ first | Basis |
|---|---|---|---|---|
| DRB1 | 60 | 20 | 0.33 | median *r* = 0.29 over eight series |
| DQB1 | 40 | 10 | 0.25 | median *r* = 0.33, discounted for one-field unreliability |
| B | 20 | 10 | 0.50 | median *r* = 0.50 |
| A | 10 | 0 | — | one series, *r* = 0.12; no survival signal |
| C (typed only) | 10 | 0 | — | effect confined to presensitised recipients |
| DRB3/4/5 presence conflict | 10 | — | — | tie-breaker only |
| DQA1 alone, DPA1, DPB1 | 0 | — | — | antibody gate only |

The gate on other loci encodes the two interaction findings that point the same
way: class I matching benefit disappears once a DR mismatch is present
(Doxiadis 2007), and DR and DQ are collinear through linkage disequilibrium, so
summing both at full weight double-counts one haplotype (Charnaya 2024, where
each fell from about 1.15 to 1.08 when both entered one model).

**An `UNKNOWN` locus is charged at its worst case**, as if it carried two
mismatches. This is the rule that enforces monotonicity, and it is the same
conservative rule the policy already applies to a partially typed locus: the
worse end decides. Missing is never cheaper than known-bad, so deleting a typing
can never lower the penalty and therefore can never improve a rank. An unknown
DRB1 leaves the DR gate closed, and a DRB3/4/5 gene whose presence was never
established is charged like a conflict, for the same reason.

Note the consequence, which is intended: a locus that is unknown costs the same
as one that is fully mismatched, not more. Absence is treated as the worst the
data could be, never as worse than that.

### 6.5 Worked example

One recipient, blood group A. All five scored loci are typed on both sides, and
HLA-C is matched in every row, so the penalties below are not carrying an
unknown-locus charge (§6.4). Eight candidate donors.

| Donor | ABO | DR mm | B mm | A mm | DQ mm | Bucket | Level | Penalty | Rank |
|---|---|---|---|---|---|---|---|---|---|
| D1 | A | 0 | 0 | 0 | 0 | RANKED | KM-1 | 0 | 1 |
| D2 | O | 0 | 0 | 1 | 0 | RANKED | KM-2 | 10 | 2 |
| D3 | A | 0 | 1 | 2 | 0 | RANKED | KM-2 | 30 | 3 |
| D4 | A | 0 | 1 | 2 | 1 | RANKED | KM-2 | 70 | 4 |
| D5 | O | 0 | 2 | 0 | 0 | RANKED | KM-3 | 30 | 5 |
| D6 | A | 1 | 0 | 0 | 0 | RANKED | KM-4 | 60 | 6 |
| D7 | A | 2 | 0 | 0 | 0 | RANKED | KM-6 | 80 | 7 |
| D8 | B | 0 | 0 | 0 | 0 | ABO_INCOMPATIBLE | — | — | not ranked |

Two behaviours to notice. **D5 beats D6**: a donor with two B mismatches but a
matched DR outranks a donor whose only fault is a single DR mismatch. That is
the ordering the interaction evidence requires and the one a flat per-mismatch
score gets backwards. And **D8 is not ranked last, it is not ranked at all** —
an ABO-incompatible donor leaves the list entirely.

---

## 7. The explanation

MATCH-001 requires that the explanation "exactly reconstructs the sort keys".
That is an acceptance criterion, so the explanation is generated **from** the
sort key, not written alongside it.

Per ranked pair:

```json
{
  "direction": "donors_for_recipient",
  "recipient_snapshot_id": "...", "donor_snapshot_id": "...",
  "bucket": "RANKED",
  "km_level": 2,
  "sort_key": [0, 2, 0, 30, 0, 0, 0, "…"],
  "abo": { "recipient": "A", "donor": "O", "route": "compatible",
           "provenance": {"recipient": "LABORATORY_MEASURED",
                          "donor": "LABORATORY_MEASURED"} },
  "mismatches": {
    "DRB1": {"status": "KNOWN", "count": 0, "depth": "one_field"},
    "B":    {"status": "KNOWN", "count": 1, "depth": "one_field"},
    "A":    {"status": "RANGE", "lower": 1, "upper": 2,
             "why": "donor second allele not read"},
    "DQB1": {"status": "KNOWN", "count": 0, "depth": "one_field"},
    "C":    {"status": "UNKNOWN", "why": "not typed on either side"}
  },
  "antibody_status": "ANTIBODY_UNKNOWN",
  "crossmatch_status": "NOT_PERFORMED",
  "evidence_quality": {"DRB1": "A", "B": "B", "DQB1": "A"},
  "missing": ["HLA-C both sides", "recipient antibody profile"],
  "blockers": [],
  "next_clinical_action": "confirm typing and obtain antibody screen",
  "structural_notes": ["recipient is DRB1 homozygous: zero DR mismatch is only
                        reachable from a donor sharing that allele"],
  "policy_version": "IR_KIDNEY_SCREEN_2.0",
  "imgt_version": "3620",
  "pyard_version": "1.5.5",
  "gold_build_id": "…"
}
```

Rules: no percentage anywhere; `UNKNOWN` and `RANGE` are always shown with the
reason; the antibody and crossmatch statuses are always present even when
nothing is known, so absence is never read as clearance.

---

## 8. Equity, and why there is no matchability term

Real allocation schemes carry a matchability or mismatch-probability term
(Eurotransplant ETKAS, the UK matchability score) because a pure best-match rule
strands rare phenotypes in a queue. **This system is not allocating a scarce
organ across a queue**, and the term does not belong in its ranking, for two
reasons:

- In `rank(donors | recipient)` the recipient is fixed, so their matchability is
  a constant and cannot reorder anything.
- In `rank(recipients | donor)` a matchability term would make one recipient's
  position depend on other recipients' records, which breaks the determinism
  contract and is not something a pre-screen should do.

The equity risk is real nonetheless, and is handled outside the ranking:

- **Homozygosity is explained, not scored.** A DRB1-homozygous recipient can
  reach zero DR mismatch only from a donor sharing that allele. The explanation
  carries a `structural_notes` entry saying so, so a structural one-mismatch is
  not misread as a poor donor. This is a real access problem: HLA-DR homozygous
  candidates have measurably worse access (sub-hazard 0.83 at one DR mismatch,
  1.40 at two), and São Paulo had to change its algorithm because DR-homozygous
  candidates accumulated on the waiting list.
- **No silent truncation.** Every list reports the total gate-eligible count and
  is pageable to the end. A "top 10" is a display choice, never a filter that
  hides candidates.
- **The blood-group floor is shown** (section 2), so a group-O recipient's
  shorter list is attributable.

**Population structure is the honest limitation.** Every coefficient here comes
from North American, European or Australasian registries. The review found that
DR matching gave no measurable benefit in Black recipients in the UK registry,
attributed to low-resolution typing failing to capture compatibility across
populations, and Iranian allele and haplotype frequencies differ from all of
them. Local calibration needs Iranian outcome data that does not exist yet. This
is stated in the output, not buried here.

---

## 9. Reproducibility

Per `HLA_VALIDATION_SPEC` section 8, every MatchRun stores the HLA reference
version, the matching policy version, the normalisation library version and the
input typing resolution.

- **MatchSnapshot is write-once.** New evidence produces a new snapshot id; old
  snapshots stay readable so a past run can be re-explained. Each clinical field
  carries its evidence block (tier, evidence group, document digest, value
  boxes) copied rather than referenced, so a later re-review cannot silently
  change what a past run saw.
- **Determinism.** The same snapshots plus the same policy version produce a
  byte-identical ordering. Ties are common — 1,974 profiles share a genotype
  with another profile — so the final tuple position is a stable identifier
  hash. The clock is an injected argument, never read inside ranking.
- **Compensation isolation is structural.** The snapshot type has no field for
  compensation, and the matching package may not import it. This is enforced by
  `scripts/architecture_lint.py`, not by convention.

---

## 10. What HA-004 must decide

The structure above (sections 3, 4, 5, 7, 9) is engineering and is decided. The
clinical content below is not, and the spec cannot be frozen until an Iranian
transplant immunologist rules.

| # | Question | Default in this design |
|---|---|---|
| M1 | Is DR ranked ahead of DQ at one-field resolution? | yes |
| M2 | Are the KM levels the right re-cut of the UK levels, and is the DR gate correct? | yes |
| M3 | Should other loci be halved once DR is mismatched? | yes |
| M4 | Is DQ binary at one-field resolution, or graded? | binary |
| M5 | Is HLA-C weighted only when typed, never imputed from B? | yes |
| M6 | May a null-suffixed DRB3/4/5 allele ever feed matching? | no (HA-011b) |
| M7 | Which loci do Iranian laboratories type, at what resolution, and how is DQ reported? | unknown |
| M8 | Is a two-field re-typing path available for shortlisted pairs? | unknown |
| M9 | Is the worse end of a range the right conservative default? | yes |
| M10 | Are the tie-breaker magnitudes acceptable as a versioned engineering policy? | yes |
| M11 | Is host-versus-graft counting over distinct donor alleles the right convention, including for a homozygous donor? | yes (standard practice, not measured here) |

The clinician-review packet for these questions is specified in the execution
plan.

---

## 11. Carried forward from V1, unchanged

- No user-facing compatibility percentage.
- Recipient preference claims (donor sex, age, city) are stored as
  `USER_PREFERENCE_CLAIM` and never alter the biological rank; they may filter
  or annotate a list after ranking, and the biological order stays visible.
- Matching has no permission or import path to compensation records.
- Low-resolution typing is never promoted to high resolution.
- OCR and any model produce proposals, never a laboratory verification.
