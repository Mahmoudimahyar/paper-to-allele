# ADR 0009 — Per-family rules, independent confirmation, and the golden protocol

**Status:** ACCEPTED (2026-09-02)
**Extends:** ADR 0007 (relations, not coordinates), ADR 0008 (extraction gates)
**Answers:** `EXTRACTION_REVIEW_2026-09-02.md` sections P1–P4

## 1. Template discovery was measuring the patient, not the form

Discovery assigned **707 of 23,485** documents to a family while one laboratory
accounts for about two thirds of the corpus. Three causes, all reproduced:

* The signature counted the grouped `DRB3/4/5` row's **values** as form labels.
  12,178 of 12,641 standalone `DRB3` boxes sit on that header's row, where they
  are the patient's presence typing, so one form split into at least seven
  "templates" by genotype and 4,262 documents fell into groups too small to
  cluster.
* It clustered in **absolute page coordinates**. The `HLA-A` label spans y 0.165
  to 0.408 between the 10th and 90th percentiles on hand-held photographs, so
  one form fragments into position blobs.
* Anchor purity then failed on those value-bearing "labels".

**ADR 0007's `DRB4` "in two columns 0.285 apart" was this all along.** `DRB4`
sits at x 0.709 when `DRB3` shares its row and 0.474 when it is alone. That was
never two sub-templates; it was one row with a variable number of values. The
conclusion ADR 0007 drew from it — store relations, not coordinates — remains
right for other reasons, but its evidence was an artefact.

### Decision

A form's signature is the position of the labels the **form** prints in a fixed
place: `A`, `B`, `C`, `DRB1`, `DQA1`, `DQB1`, `DPA1`, `DPB1`. Documents are
compared by fitting an isotropic scale and offset, with the residual expressed
as a fraction of the form's own extent so the threshold means the same thing
however a prototype was built. Three labels are required, because two determine
a fit exactly. Ties are refused.

**Building this reproduced the bug it fixes.** Greedy agglomeration at a tight
threshold split one form into nine prototypes whose mutual residuals were inside
the assignment tolerance; every document then fitted several and 4,096 were
refused as ambiguous. Prototypes that fit each other are one form and are merged.

Coverage: **707 → 12,300 documents (52.4%)** in three printed forms, and 75% of
the documents carrying three or more form labels.

## 2. A per-family rule, gated on a measured property

The default relation caps the value chain at 20 anchor heights. On the dominant
form the second allele column sits 8–25 heights away, so the cap cuts it off:
3,800 of the assigned documents' cells resolved with one allele.

The family rule reads the whole row band with **no distance cap** and requires
each value to print its own locus. The prefix requirement, not the distance, is
what makes that safe — and it is **measured per family rather than assumed**:
99.8–99.9% on all three forms. The first measurement said 65% because it counted
every parseable box on the page, including dates and sample numbers; the
property is about values bound in a cell.

| on the 12,300 assigned documents | default | family rule |
|---|---|---|
| resolved cells | 28,783 | **39,606** |
| two-allele cells | 24,983 | **39,511** |
| single-allele cells | 3,800 | **95** |
| nomenclature-impossible values | 0 | **0** |
| one box bound by two loci | 0 | **0** |
| DRB1↔DRBX disagreement | 7 / 4,975 | 27 / 7,923 |

The disagreement rate rises from 0.14% to 0.34% on a 59% larger checkable base,
and every one of those goes to review rather than into the database.

A document whose form is not recognised keeps the default. Claiming a family
would apply its authored rule to a layout it was never measured on.

## 3. The golden corpus: a protocol, not a spreadsheet

**The unit is the cell.** 199 documents hold 2,189 cells, 948 of them resolved.
Zero failures over 948 bounds false acceptance at **0.32%** by the rule of
three; the document as a unit could only ever bound it at 1.5%.

**The labeller never sees the machine's answer.** It is written to a separate
file the labelling page does not load. A proposal beside a blurry crop is an
anchor, and an anchored labeller measures agreement rather than truth. A
contract test asserts the page cannot reach it.

**Two people label, a third adjudicates.** Double entry by a *different*
operator detects 88.3% of errors against 69.0% for the same operator twice;
letting the two entrants reconcile makes the entries match, sometimes by
introducing new errors. Each annotator's name seeds a different order.

**Only two outcomes are failures**: a cell resolved to a value the human read
differently, or resolved at all where the human could read nothing. Abstaining
where a value exists is a *miss* — an incomplete record is a cost, a wrong one
is a harm. `scripts/golden_score.py` exits non-zero on a single failure, and
also on an empty corpus, so an unlabelled set cannot read as a clean bill of
health.

## 4. Confirmation by an independent engine

ADR 0006 requires unanimity across architecturally independent recognizers,
having measured that a 2-of-3 majority across neural engines is *worse* than
unanimity (3.50% against 4.50% false acceptance): engines sharing an
architecture share their mistakes, so a majority of them is one opinion counted
three times.

Tesseract is the independent one available. Cells are re-cropped from the
original at the anchor-defined geometry, not from the primary engine's box.

Two decisions came from measuring:

* **The whitelist must include letters.** Digits alone confirmed 20.8% of cells,
  because the forms that print the locus on every value show `DRB1*11`.
* **The confirmer confirms digits, not the locus.** Requiring its prefix to
  parse withheld 130 of 400 cells where `DRB1*11` had been rendered `RB1*11` and
  the digits were perfectly clear. The locus came from geometry and the primary
  pipeline already refused any value naming a different gene. A prefix read
  clearly and naming another gene still contradicts.

**The vocabulary gate applies to both engines.** Every contradiction the design
pass measured was Tesseract reading a family that does not exist for the locus,
so an impossible reading withholds rather than voting against a possible one.
Three outcomes: `CONFIRMED` (auto-accept candidate), `CONTRADICTED` (review
budget), `UNCONFIRMED` (no second opinion; the value stands on the primary
engine alone).

**Measured result is well below what was predicted, and is reported as
measured.** A design pass reported 86.3% agreement on a 300-cell DRB1/DQB1
sample; across all eight loci the confirmation rate is far lower. The gap is not
explained — the smaller `C` and `DQA1` cells are a candidate — and it is not
worth closing by tuning, because the confirmer's value is settled by the golden
corpus and not by its own agreement rate.

## 5. What none of this establishes

No number here is an accuracy. The pipeline is now self-consistent, gated, and
independently spot-checked, and it still has never been compared to a human
reading (KI-012). Everything above is a yield, an internal-consistency rate, or
an agreement rate between two machines. **HA-007** is the work that changes
that, and until it is done nothing may be published to Gold.
