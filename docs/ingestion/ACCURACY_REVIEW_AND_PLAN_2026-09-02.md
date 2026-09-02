# Accuracy review and improvement plan — 2026-09-02

**Scope:** everything built so far for turning the unique images into a database:
Latin OCR pass, Persian pass, template discovery, anchor-based locus resolution,
golden sampling, and the donor/recipient question. Every number below was
measured on this machine against the real archive today; measurement scripts ran
inline and printed counts only. Nothing here has been validated against human
ground truth yet — that is the first finding.

## 1. Verdict

The pipeline is fast and complete (0 failures over both passes) but **not yet
accurate, and the numbers we have been quoting were not accuracy numbers.** Four
things were wrong, one of them silently dangerous:

| What we believed | What is true | Consequence |
|---|---|---|
| 33,147 unique images; ~30% at 520 px; a "low-resolution tail" of 9,666 documents | **23,566 unique originals; 90% above 900 px; 85 documents ≤560 px.** 9,581 rows in the OCR pass are `…_thumb (n).jpg` files — thumbnail *copies* whose originals all exist on disk. The manifest filter excluded `_thumb.jpg` but not `_thumb (n).jpg`. | Golden sample: 54 of 199 documents are thumbnails (the entire low-res stratum). HA-003's "77% at 520 px" premise is false. 1,164 Persian-pass images and 373 template-family members are thumbnails. |
| Locus resolution "resolves 34–44%" for DRB1/DQB1/DPA1/DPB1 | Under the current `below` rule, **of 2,977 DRB1 RESOLVED bindings only 185 are value-shaped and 988 are the next row's label**; DQB1: 111 values vs 3,573 labels; DPA1 and DPB1: **zero** value-shaped bindings. | The resolver, run at scale, would have bound the wrong token to the locus for most documents. This is the failure `OCR_SPEC.md` §2 exists to prevent, and no yield metric could have shown it. |
| Strict label anchors exist on 9,790 documents; 44% of reports are "merged-only" (`DRB1*11` in one box) | The recognizer reads the trailing `1` of `DRB1/DQB1/DPA1/DPB1` as capital `I` in **60,995 boxes** (`HLA-DPBI` 7,174 times) and `DRB5` as `DRBS`. With a label canonicaliser, documents with ≥2 anchors rise **9,790 → 18,531**, and "merged-only" falls from 44% to **3.6%**. | Anchor coverage was crippled by one glyph confusion. Template discovery used the strict regex and must be re-run. |
| py-ard pinned at 2.4.0 with IMGT 3650 | Locked version is **1.5.5** (`py-ard>=1,<2`). `init(imgt_version="3650")` fails with `IndexError`; 3620 loads. `validate("DRB1*11")` rejects first-field-only alleles by design. | The spec's 3.65 pin is unimplementable as locked; first-field vocabularies must be derived from the allele table. |

The good news is equally concrete: two **label-free accuracy checks** now exist
and both are strong — image-ABO vs caption-ABO agree **96.6%** (n = 4,293), and
the lab form's own printed role field agrees with the caption keyword **98.6%**
(n = 4,694). And the value-side errors are systematic, not random, which means
they are fixable by rule rather than by a better model.

## 2. Findings by component

### 2.1 Recognition (OnnxTR `crnn_mobilenet_v3_small`)

Errors are dominated by a small confusion set, measured over 88,643
allele-value-shaped boxes on true originals:

- **20.7% of value boxes carry a letter in a digit slot**: `I→1` 10,465, `L→1`
  7,052, `S→5` 6,845, `l→1` 3,156, `o→0` 2,648, `O→0` 813. Top shapes `II`
  (=11), `nL`, `LS` (=15), `SS`.
- The `*` separator is read as `+`, `°`, `-`, `"`, `'` in ~3,700 boxes.
- The same `1→I` confusion hits **labels** (60,995 boxes) and `5→S` hits `DRB5`.
- In ABO cells, `O` is read as digit `0` in 2,804 boxes — which is why O+ looked
  under-represented (12% vs ~33% expected). Adding the `0+` boxes restores it.

These are exactly the confusions ADR 0006 anticipated. The remedy it prescribes —
**mask the CTC logits to the cell's grammar** (digits, `:`, `*` for value cells;
locus alphabet for label cells) — has not yet been applied. A post-hoc
canonicaliser is the cheap interim and is safe *inside* a cell whose grammar is
known; it is never safe on free text.

### 2.2 Locus binding (`src/kidneymatch/ocr/anchors.py`)

The resolver is correct by construction for what it checks (13 TDD tests) but
was pointed at the wrong geometry and lacks a value-shape gate:

| locus | `below`, gap 2.5 RESOLVED | of which value-shaped | of which the next label | row rule RESOLVED | value-shaped | label-shaped |
|---|---|---|---|---|---|---|
| DRB1 | 2,977 | 185 | 988 | 13,985 | 8,877 | 118 |
| DQB1 | 3,999 | 111 | 3,573 | 12,528 | 7,862 | 119 |
| DPA1 | 4,445 | 0 | 3,901 | 507 | 43 | 16 |
| DPB1 | 3,991 | 0 | 3,884 | 391 | 30 | 27 |

Row rule = same row band (|Δy| ≤ 1.0 label-height), to the right, any distance,
canonicalised anchors, true originals only (n = 23,485). The 2-D layout around
the DRB1 anchor on Yekta forms confirms it: other locus labels sit at Δx = 0 and
Δy = −4…+12 (a vertical stack of row labels), and value-shaped boxes are **not**
near the anchor vertically. DPA1/DPB1 are laid out differently and need their
own authored rule; the numbers above must not be read as their ceiling.

The remaining row-rule bindings that are neither value- nor label-shaped are
values with glyph damage in the prefix or separator (`DRBI*II`, `DRB1+11`,
`DRB1°11`), recoverable under P1(e).

Nomenclature is a weak but free guard: among merged `LOCUS*nn` boxes the first
field is impossible for the claimed locus in 0.5% (DRB1) – 0.7% (DQB1) of cases.
It cannot catch `DRB1↔DQB1` swaps on 03/04, which both loci share.

### 2.3 DRB3 / DRB4 / DRB5

10,951 documents print exactly one combined header. The row is **horizontal**:
`DRB3/4/5` | *gene name* (`DRB3`, `DRB4`, `DRB5`, read as `DRBS` 566 times) |
allele. The box *below* the header is the next row's label (`HLA-DPBI`, 7,174
times). The gene is therefore printed as the row's **value** — presence typing —
and reading it from the token is permitted only because the header enumerates
the admissible set. Rule in P1(f). Biology for *validation only*: DRB1\*03/11/12/
13/14 haplotypes carry DRB3; \*04/07/09 carry DRB4; \*15/16 carry DRB5;
\*01/08/10 carry none; exceptions exist. py-ard's `dr_blender` flags
inconsistency; it must never fill, choose, or correct.

### 2.4 ABO

- Image: 9,677 true originals have exactly one ABO-shaped box (270 have more
  than one → review).
- Caption: 36.2% of images have a consistent caption ABO, 0.1% conflicting.
- Where both exist (n = 4,293): **96.6% full agreement**, 1.5% Rh differs, 0.9%
  letter differs, 1.0% both. The disagreements are `+` read as `-` (lost
  vertical stroke) and `A`/`O` confusion — the recognizer, not the caption.

### 2.5 Donor vs recipient — the distinction the user asked for

The role is **not** decided by who posted the image. Measured on the corrected
set of 18,615 typing reports (true originals, ≥2 canonical loci):

| evidence, in order of authority | reports | share |
|---|---|---|
| 1. **Printed on the form** — `نسبت: اهدا کننده پیوند / گیرنده پیوند` read by the Persian pass (fuzzy variants: `کیرنده`, `هدا/امدا کننده`, `کاندید پیوند`) | 7,903 | 42.5% |
| 2. Caption keyword, unambiguous, across every message posting the image | 7,085 | 38.1% |
| 3. Sender ≥95% single-role over ≥3 posts (a *prior*; needs review) | 883 | 4.7% |
| ✗ Caption carries both role words, or posts conflict | 955 | 5.1% |
| ✗ No evidence at all (photo-only message, orphan bundle) | 1,789 | 9.6% |

**80.5% is decidable without a prior.** Checks that make this trustworthy:

- Form field vs caption keyword on 4,694 documents that have both: **98.6%
  agree**. The dangerous direction — form says RECIPIENT, caption says DONOR —
  occurs 44 times (2.5% of form-recipients); the reverse 24 times.
- Conflicts *across posts* of the same image are rare: 0.1–0.2%. The
  broker-repost fear was overstated; the real gap is images posted with no text.
- Bundle context (same sender within ±120 s) recovers essentially nothing;
  ±1 h recovers ~5 points at the cost of ambiguity. Not worth the risk.
- Of no-caption reports with a known sender, 31.4% come from mixed-role
  (broker-like) senders — a sender prior is indefensible there and those must
  stay `CANDIDATE_AD_UNKNOWN_ROLE`.
- Message-level keyword rates (49.4% donor-only / 18.1% recipient-only / 10.1%
  both / 22.3% neither over 145,694 photo messages) overstate ambiguity: "both"
  is mostly an *addressee* artefact (a donor ad says "buyer, call me").
- ABO must never be used for role. Age on the form is a strong plausibility
  check (donor programme range 20–40) but is a flag, not a decision.

### 2.6 Persian pass, template discovery, golden sample

- Persian pass bought names *and* — unexpectedly — the printed role field and a
  transplant-history field. 1,164 of its 20,201 rows are thumbnails.
- Template discovery: 5 verified families / 613 documents were found with the
  strict label regex; 373 members are thumbnails (2 in verified). Re-run with
  canonical labels on true originals before any family is used.
- Golden sample must be **redrawn** after P0/P1: it selects documents, but 54 are
  thumbnails and its low-res stratum no longer describes the corpus.

## 2.7 What was fixed on 2026-09-02 (ADR 0008)

P0, P1, P4 and P5 of the plan below are **implemented and measured**. Results:

| change | before | after |
|---|---|---|
| documents with 3+ locus anchors | 3,873 | **17,041** |
| DRB1 / DQB1 resolved, all gates on | 185 / 111 value-shaped | **9,700 / 10,061** |
| HLA-A / -B / -C resolved | 0 (values were dropped) | **10,967 / 9,411 / 3,038** |
| DRB3/4/5 per-gene facts | 3 | **29,820** over 12,488 documents |
| ABO read from an anchored cell | shape-only, O at 12% | **2,995 documents**, O+ 28.9% |
| role from the printed field | not built | **tiered, with the caption as veto only** |

Two external consistency checks, neither of which existed before:

- The DRB1 haplotype constraint agrees with the independently-read DRB3/4/5 row
  on **99.62%** of the 5,326 documents where both were read.
- The anchored ABO distribution matches the Iranian population, where the
  shape-only reading did not.

**Three findings changed what the product can promise.** These laboratories
print DQA1, DPA1 and DPB1 rows and leave them blank (KI-013), so the archive
supports DR/DQB-prioritised matching and not DP. The dominant letterhead
disclaims its own blood-group field as patient-reported (KI-014), so a printed
ABO is not a laboratory measurement. And a whole-page search for the English
words "donor" and "recipient" would have inverted the role on hundreds of
documents; only a value in an identified cell counts.

**What is still not measured (KI-012):** no extracted value has been compared to
a human reading. P2 and P3 below are untouched, and they are what converts every
number here from a yield into an accuracy.

## 3. The plan, in order of accuracy gained per hour

Effort: A = agent-days, H = human-hours (H figures are estimates). Everything
test-first; every step ends with a measured before/after on the real corpus.

**P0 — Data integrity (0.5 A, 0 H).** Fix the manifest filter (`"_thumb" in
name`) — done in this commit with a regression test. Mark the 9,581 thumbnail
rows in `ocr_pass.sqlite` as `THUMB_COPY` by `rel_path` (do not delete; the
pass is immutable evidence). Re-run template discovery on true originals with
canonical labels. Rewrite HA-003 and `CURRENT.md`'s resolution facts.

**P1 — Resolver correctness (1–2 A, 0 H). Do this before anyone labels.**
(a) Label canonicaliser inside `find_anchors`: trailing `I/l/L/|→1`, `S→5`,
only in the label position; tests: `DRBI` anchors DRB1, `DRBS` anchors DRB5,
`DRBI*II` is *not* an anchor. (b) **Value-shape gate**: RESOLVED requires every
bound token to match the value grammar; a label-shaped token is
`REVIEW_REQUIRED`, never a value. (c) Row rule as the default relation; DPA1/
DPB1 and each family get authored rules stored in the registry (ADR 0007).
(d) Prefix consistency: a value carrying a locus prefix that differs from the
anchor → REVIEW. (e) Value canonicalisation limited to the cell grammar (`*`
variants, digit-slot glyphs), raw token preserved with the normalisation
recorded — then measure against **CTC logit masking** on the stored crops, which
ADR 0006 already prescribes and which removes the confusion at source. (f)
`GROUPED_DRBX` anchor type: header regex, candidates on the row band matching
`^(HLA-)?DRB([345])(\*\d{2,3}(:\d{2,3})?)?$`, one PRESENT fact per gene, >2
tokens → REVIEW, `DRBS`/bare numbers → REVIEW; `dr_blender` inconsistency →
flag both rows. (g) Merged-box anchor for the residual 3.6%, only when the box
position agrees with the family's locus position. (h) Replace the 34–44% table
in `OCR_ENGINE_BENCHMARK` with the shape-gated one.

**P2 — Validation gates (1 A).** Resolve the py-ard/IMGT conflict (HA-006):
either pin an IMGT release 1.5.5 loads (3620 verified) or upgrade py-ard and
re-test; derive per-locus first-field vocabularies from the allele table; use
`validate()`/`redux()` only for two-field strings; serology accepted only where
HA-004 says the family reports antigens; never expand resolution.

**P3 — Labelling tool and golden labelling (1–2 A; 5–9 H).** Unit = the
(document, locus) cell, pre-generated from corrected anchors, with
`NOT_PRINTED` / `UNREADABLE` / `PRESENT_ONLY`. Crop-first, **blind** to the OCR
proposal, constrained pick-lists from the per-locus vocabulary, double entry by
two different people, third-person adjudication against the image. Per-document
fields: class, family, lab, date, ABO-on-form with Rh, **role-on-form** with a
"word is a field label, not the subject" flag, and caption ABO/role as separate
claims. Redraw the 199 on the corrected corpus; ~440 cells bound wrong-locus
false acceptance at ≤0.68% (rule of three); then expand *adversarially* — the
DRB1↔DRBX-inconsistent documents, digit-conflict copy pairs, `DRBS`-bearing
documents, prefix-conflict documents, mixture families — to ≥598 then ~3,000
cells. Cells within a family are not independent for rule errors: require zero
rule-level failures per family, not just a per-cell bound.

**P4 — Role classifier, CLASS-001 (2–3 A; validation inside P3).** Evidence
hierarchy exactly as §2.5: printed form field (same-line geometry, value left of
label in RTL, fuzzy variants) → recipient-only test types (PRA/DSA/Luminex/
crossmatch ⇒ RECIPIENT) → caption of the **original** author (forwarded-from),
with the expanded lexicon and addressee handling → sender-purity prior as a
reviewable proposal → otherwise `CANDIDATE_AD_UNKNOWN_ROLE`. Any conflict
between form and caption → `UNKNOWN_ROLE` + review. Store role as a
document-level fact with provenance so it survives reposts. Acceptance: ≥300
true recipients in the evaluation set with **zero** recipient→donor errors
(<1% one-sided 95% bound). A fine-tuned Persian encoder (FaBERT/ParsBERT,
300–600 labelled captions, fp32 on the 1070) can later attack the 5.1%
ambiguous stratum; its ceiling is ~10 points, so it comes after P0–P3.

**P5 — ABO reconciliation (0.5 A).** Store the image claim and the caption
claim separately with provenance; `0→O` only inside an ABO cell; agreement →
accepted (still S1 if low-res); image-only → proposal; caption-only → source
claim, unverified; conflict → `ABO=CONFLICT`, review, and a signal that the
caption's subject may not be the document's subject. Rh is never synthesised.

**P6 — Batch extraction with a prioritised review queue (2–3 A; standing
review).** Queue order: prefix-conflict > DRB1/DRBX-inconsistent > digit
conflicts across copies of the same report > single-read low-res. Cross-copy
agreement is a *priority* signal only — group copies by image similarity, not
by OCR tokens, and count independent captures, never recompressions.

**Not to be done:** infer DRB3/4/5 from DRB1; promote serology to molecular or
first-field to two-field; use ABO or poster identity to decide role; let any
model make the final finding; re-run the full 2.1 h Latin pass — only value
crops need re-decoding.

## 4. Human decisions

- **HA-003 (rewrite):** the ≤560 px band is 0.4% of unique originals, not 30%.
  The decision still matters for the 561–900 px band (9.7%) and for the
  `_thumb.jpg` files the export carries for every photo.
- **HA-004:** unchanged; governs serology acceptance in P2.
- **HA-006 (new):** py-ard 1.5.5 cannot load IMGT 3650; the spec pins 3.65.
  Choose: pin 3620 with the locked library, or upgrade py-ard (major version) and
  re-test. Recorded in `HUMAN_ACTIONS.md`.

## 5. Provenance of the numbers

All counts computed 2026-09-02 from `data/derived/ocr_pass.sqlite`,
`data/derived/persian_pass.sqlite`, `data/derived/template_families.json`,
`data/derived/golden_sample.json` and the export HTML, on this machine, with
sender names hashed on read and no text printed. Research inputs (Persian
lexicon, labelling-protocol evidence — Kawado 2003, Barchard 2020 — and DRB
haplotype biology from hla.alleles.org and py-ard `blender.py`) are summarised
in the session artefacts; items the research could not verify are listed there
and were not used as facts here.
