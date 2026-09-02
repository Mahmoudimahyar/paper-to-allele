# ADR 0008 — Extraction gates, glyph repair, and what the corpus actually reports

**Status:** ACCEPTED (2026-09-02)
**Extends:** ADR 0007 (the registry stores relations, not coordinates)
**Supersedes:** the resolve-rate table in `OCR_ENGINE_BENCHMARK_2026-09-01.md`

## The measurement that forces this

ADR 0007's relation-based registry was right. The rule it shipped with was not,
and nothing checked what the rule bound. A shape audit of the 23,485 analysable
true originals found that of 2,977 `DRB1` bindings the resolver called RESOLVED,
only **185 were allele-shaped and 988 were the next row's locus label**. `DPA1`
and `DPB1` produced **zero** value-shaped bindings. Every one of those would have
entered the database as a patient's HLA typing.

No yield metric could see it. The resolver reported success every time.

## Decision 1 — four gates stand between a candidate box and a value

1. **Value shape.** A bound token must parse as an allele value. A label-shaped
   token can never be a value, however damaged.
2. **Prefix consistency.** A value that carries its own locus name must agree
   with the anchor. Geometry still decides the locus; disagreement means nobody
   does, so a human looks.
3. **Nearest-anchor ownership.** A candidate that is closer to a different
   locus's label, and aligned with it, belongs to that label.
4. **Cardinality.** A locus has at most two alleles.

## Decision 2 — alignment is measured by overlap, not by centre distance

A `DRB1` value's centre sits 0.5 to 0.75 label heights **above** its label's
centre while the two boxes still share 25–50% of their vertical extent. A centre
tolerance loose enough to admit them also admits the neighbouring row. Overlap
separates the two and does not care that the recognizer boxed the value higher.

The default relation is `direction="right"`, `align_overlap=0.2`, `max_gap=20`
label heights, `max_values=2`. **These numbers must be validated against the
golden corpus, not tuned by yield.** A grid search finds a slightly looser
overlap resolves more; that is not evidence it is right.

## Decision 3 — glyph repair, bounded by the cell's grammar

The recognizer reads the trailing `1` of `DRB1/DQA1/DQB1/DPA1/DPB1` as capital
`I` in 60,995 boxes — `DRBI` outnumbers `DRB1` **3.5 to 1** — and `DRB5` as
`DRBS`. Inside allele values, 20.7% of boxes carry a letter in a digit slot.

Repair is legitimate only inside a cell whose grammar is already fixed by
geometry. Two asymmetries make it safe:

* **Accepting an anchor is strict.** Only the final character is repaired.
  Interior damage (`DRRI`, where `B` was read `R`) is refused: it would add
  about 1% more anchors and it is the only mechanism by which `DRB1` could
  become `DPB1`.
* **Rejecting a value is permissive.** `DRRI` is refused as a value even though
  it cannot anchor a locus. Refusing costs recall; accepting emits a patient
  allele of `DRRI`.

Effect: documents with three or more locus anchors rise from 3,873 to 17,041.

### `DRBS` is `DRB5`, and how the disagreement was settled

Two independent design passes reached opposite conclusions. One argued from
prior odds — a likelihood ratio of 30 against a 2.66:1 prior gives 92%
confidence, so abstain. The other argued from the grouped row's internal ground
truth and reached the opposite.

The question was settled by direct measurement against the **DRB1 row**, read by
a different anchor, a different relation and a different part of the page, using
the haplotype constraint that `DRB1*15/*16` carry DRB5 while
`*03/*11/*12/*13/*14` carry DRB3:

| standalone label | n | DRB1 expects DRB5 | expects DRB3 |
|---|---|---|---|
| `DRB5` | 1,142 | 99.6% | 48.4% |
| `DRBS` | 1,020 | **99.2%** | 47.8% |
| `DRB3` | 5,830 | 17.7% | 99.9% |

`DRBS` is indistinguishable from `DRB5` and nothing like `DRB3`. The prior the
model assumed does not describe the `DRBS` population. **A measurement against
independent ground truth outranks a model, and where they disagree the model is
what gets discarded.**

## Decision 4 — the grouped `DRB3/4/5` row is presence typing, read rightwards

The row prints gene NAMES, not alleles: the box at rank 0 to the right of the
header is a gene name 95.7% of the time and an allele 0.1%. Reading downward —
the previous rule — lands on the next row's locus label in 88.9% of cases.

Reading the gene from the token is licensed **only** because the header prints
the admissible set `{DRB3, DRB4, DRB5}`; geometry still fixes which cell is
being read. Every partial header is refused, because the moment the enumeration
is not printed the licence is gone.

`ABSENT` is emitted only when two gene tokens account for both haplotypes
(0.09% discordance against DRB1). With one token the other genes are UNKNOWN —
calling them absent is wrong 5.90% of the time. An empty row is never ABSENT.

Effect: 12,488 documents yield 29,820 per-gene facts, against 3 before. An
independent haplotype check via py-ard's `dr_blender` agrees on **99.62%** of
the 5,326 documents where both rows were read.

## Decision 5 — the role is a document fact, read from the printed field

`CLASS-001`. A whole-document text search inverts the role at scale: 517
documents contain both English role words, and 142 contain "Recipient" while the
printed field says DONOR. Only a value in an identified cell counts. Three
confidence tiers, because the field label is recognised on only 810 documents;
the weakest tier contradicts recipient-only serology 20% of the time and is a
proposal until corroborated. A caption may corroborate or veto but never
override the printed field. ABO, age, sex and poster identity contribute
nothing.

## Decision 6 — an ABO-shaped box is not a blood group, and this form disclaims it

A token is a blood group only inside a cell located by a printed field label;
shape alone may raise a review item and never a value. Read that way, the
distribution becomes O+ 28.9%, A+ 28.3%, B+ 23.8%, AB+ 6.8% — consistent with
the Iranian population, where shape-only reading had put O at 12% because the
recognizer reads `O` as the digit `0`.

**The dominant letterhead prints a disclaimer**: "information regarding the
blood group is based on the attendee's own account, and the laboratory bears no
responsibility for its accuracy" — 2,928 documents, 97.7% of them Yekta. Such a
value is `PATIENT_REPORTED_ON_FORM`, may never satisfy a requirement for a
laboratory-verified ABO, and its agreement with the caption is **not**
independent corroboration, because both claims can descend from the same
person's statement. `MATCH-ABO-001` must respect this.

## What the corpus actually reports

Resolved locus cells over 23,485 documents, all gates on:

| locus | resolved | note |
|---|---|---|
| A | 10,967 | |
| B | 9,411 | |
| DQB1 | 10,061 | |
| DRB1 | 9,700 | |
| C | 3,038 | row printed, cell empty on 10,833 |
| DQA1 | 763 | row printed, cell empty on 11,284 |
| DPA1 | 31 | row printed, cell empty on 12,595 |
| DPB1 | 31 | row printed, cell empty on 12,739 |

Plus 17,480 DRBX `PRESENT` and 12,340 `ABSENT` facts.

**These laboratories print DQA1, DPA1 and DPB1 rows and leave them blank.** The
low numbers are not a rule failure — `DRB1` under the same rule has an empty
cell on 3,662 documents, `DPB1` on 12,739 of 12,770. That is the lab not typing
DP, and it means the archive supports DR/DQ-prioritised matching (KI-004) and
does not support DP matching at all.

## What is still not measured

Every number above is a yield or an internal-consistency rate. **No extracted
value has been compared to a human reading.** The golden corpus is drawn (199
documents, thumbnail-free, all five verified families covered) and unlabelled.
Wrong-locus false acceptance remains unmeasured, and `OCR-001` cannot leave
`BLOCKED_BY_BENCHMARK` until it is.
