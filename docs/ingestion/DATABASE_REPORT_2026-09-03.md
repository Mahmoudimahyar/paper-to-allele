# What is in the database, measured 2026-09-03

Every number here is a **count of documents**, or an agreement rate between two
machines. None is an accuracy: no extracted value has yet been compared to a
human reading (KI-012), and that is what HA-008 and HA-007 are for.

Source: `data/derived/facts.sqlite` (extraction `facts/v1`) and
`data/derived/source.sqlite`, both gitignored and local.

---

## 1. The headline caveat: this is not yet a database of people

The unit is the **image**, not the person. Entity resolution (`ENTITY-001`) has
a spec, a measured frequency table and a module, but the clustering has not been
run, so "how many unique donors" has no exact answer yet. What can be said:

| | documents |
|---|---:|
| unique original images | 23,566 |
| …typed on at least one HLA locus | 14,625 |
| …typed on three or more core loci (A/B/C/DRB1/DQB1) | 10,032 |
| distinct HLA fingerprints among those | **4,246** |
| the same image posted more than once | 110,050 postings of 23,565 images (mean **4.7**) |

**4,246 is the best current estimate of distinct people typed on three or more
loci**, and it is an estimate in both directions:

* it is an **over**-count where one person's report was photographed twice and
  read slightly differently, so the two copies carry different fingerprints;
* it is an **under**-count where two unrelated people coincide — at three loci
  that happens once in 22,000 to 218,000 pairs, which over 50.3 million pairs is
  not negligible (see `ENTITY-001`).

Fingerprint group sizes: 2,238 appear on exactly one document, 1,716 on two to
five, 292 on six or more, and the largest group covers 67 documents.

## 2. Donor and recipient

Role comes from the form's own printed field, corroborated where possible by the
caption the image was posted with. A caption alone proposes and never resolves,
because the poster is frequently a broker rather than the subject.

| role | documents |
|---|---:|
| **DONOR** | 4,584 |
| **RECIPIENT** | 2,937 |
| proposed, needs review | 9,767 |
| no evidence at all | 6,278 |

Restricting to documents that are actually usable for matching — a role **and**
A+B+DRB1 resolved:

| | documents |
|---|---:|
| **donors with a role and A+B+DRB1** | **2,983** |
| **recipients with a role and A+B+DRB1** | **1,726** |
| total | 4,709 |

The donor-to-recipient ratio of roughly 1.7 : 1 is what a market of
advertisements looks like, not a clinical population; it should not be read as
supply and demand.

## 3. How complete is the HLA data?

### Loci resolved per document

| loci resolved | documents | cumulative (≥) |
|---:|---:|---:|
| 6 | 97 | 97 |
| 5 | 2,030 | 2,127 |
| 4 | 5,165 | 7,292 |
| 3 | 2,954 | 10,246 |
| 2 | 2,588 | 12,834 |
| 1 | 1,791 | 14,625 |
| 0 | 8,941 | 23,566 |

No document reaches 7 or 8 loci, and that is a property of the laboratories
rather than of the pipeline: DPA1 and DPB1 are printed and never filled
(KI-013), so six is the practical ceiling.

### Per locus

"Both alleles" matters: a locus is diploid, and one value read does **not** mean
homozygous — it means one value was read.

| locus | resolved | both alleles | needs review | not tested | no label on the form |
|---|---:|---:|---:|---:|---:|
| A | 11,628 | 11,274 | 3,562 | — | 8,376 |
| B | 10,911 | 10,496 | 4,442 | — | 8,213 |
| DRB1 | 11,112 | 10,807 | 4,900 | — | 7,554 |
| DQB1 | 9,675 | 9,365 | 4,398 | — | 9,493 |
| C | 3,114 | 3,020 | 12,505 | — | 7,947 |
| DQA1 | 725 | 707 | 12,339 | — | 10,502 |
| DPA1 | 24 | 22 | 1,347 | 12,204 | 9,991 |
| DPB1 | 32 | 32 | 896 | 12,459 | 10,179 |
| DRB3 | 11,554 | presence-typed | 963 | — | 11,049 |
| DRB4 | 10,489 | presence-typed | 963 | — | 12,114 |
| DRB5 | 10,427 | presence-typed | 963 | — | 12,176 |

DRB3/4/5 are reported as present or absent, not as alleles, so "both alleles"
does not apply to them.

### Complete against the sets matching actually uses

| set | documents | with **both** alleles at every locus |
|---|---:|---:|
| A + B + DRB1 (classic 6-antigen) | 8,271 | **8,064** |
| A + B + DRB1 + DQB1 | 6,543 | **6,394** |
| A + B + C + DRB1 | 2,213 | 2,156 |
| A + B + C + DRB1 + DQB1 | 1,860 | 1,818 |

**8,064 documents carry a complete classic 6-antigen genotype.** C is the
binding constraint on anything wider: it is printed on 15,619 forms and filled
on 3,114 of them.

## 4. How many OCR engines, and how did they do

**Four engines are in production**, and 22 configurations were benchmarked to
choose them.

### In production

| engine | role | notes |
|---|---|---|
| **OnnxTR** `fast_base` + `crnn_mobilenet_v3_small` | primary detection and recognition | 2.1M params, 217 ms/image over the archive. Everything else reads its boxes. |
| **Constrained CTC decode** over the same logits | stability, not a reading | Re-reads each cell under nine one-pixel offsets. It may take a fact away; it may never create or change one. |
| **Tesseract 5** (psm 7, alphanumeric whitelist) | independent confirmer | From a different era, shares no training data with the primary — which is why its agreement is evidence. |
| **PP-OCRv5** `en_PP-OCRv5_mobile_rec` | independent confirmer, adopted 2026-09-03 | 4.1M params, 13 ms/crop on CPU, Apache-2.0. |

### How the two confirmers compare, over all 47,221 resolved cells

| reader | confirms | contradicts | no opinion |
|---|---:|---:|---:|
| Tesseract 5 | 22,778 (48%) | 6,577 (14%) | 17,866 (38%) |
| **PP-OCRv5** | **43,124 (91%)** | 3,063 (6%) | **1,034 (2%)** |

Tesseract's problem was never disagreement, it was silence: a class I value box
is four glyphs wide and it returned nothing on more than a third of them.
PP-OCRv5 gives an opinion on **17,206 cells Tesseract could not read at all**.

Where they land together:

| Tesseract | PP-OCRv5 | cells |
|---|---|---:|
| CONFIRMED | CONFIRMED | 21,745 |
| UNCONFIRMED | CONFIRMED | 15,500 |
| CONTRADICTED | CONFIRMED | 5,879 |
| UNCONFIRMED | CONTRADICTED | 1,706 |
| CONFIRMED | CONTRADICTED | 804 |

The constrained decode, separately: 44,504 UNANIMOUS, 3,584 SPLIT, 3,169
DIGITS_LOST, 237 ILLEGIBLE, plus 2,795 PROPOSAL (recorded only, never promoted).

### Benchmarked and not adopted

22 configurations on the same 600 real crops
(`OCR_MODEL_SURVEY_2026-09-03.md`), agreement with the trusted set:

| engine | trusted | hard | ms/crop |
|---|---:|---:|---:|
| Qwen3-VL 4B Q4_K_M (llama.cpp) | 0.997 | 0.910 | 982 |
| **PP-OCRv5 en-mobile-rec** | **0.970** | **0.910** | **13** |
| PP-OCRv5 mobile / server | 0.963 / 0.957 | 0.855 / 0.890 | 27 / 21 |
| Tesseract 5 | 0.900\* | 0.515\* | 8 |
| OnnxTR parseq | 0.883 | 0.755 | 16 |
| 7 other DocTR recognizers | 0.46–0.74 | 0.31–0.53 | 2–90 |

\* inflated and deflated respectively, because the strata were partly *defined*
using Tesseract's verdicts.

Qwen3-VL scores marginally higher for 75× the cost. Also tested earlier:
EasyOCR (best Persian reader, contributes no HLA values), RapidOCR, PaddleOCR's
full page pipeline (6 s/image), Surya (excluded: fp16 only, no Pascal).

Installed, smoke-tested, and left **unmeasured** after two power failures
stopped the GPU phase: GLM-OCR, PaddleOCR-VL, GOT-OCR 2.0, OlmOCR-2, TrOCR,
Qwen2.5-VL. GOT-OCR 2.5 does not exist. GLM-4.5V (~106B) cannot run here and
may not go to a cloud, which would mean sending patient data.

### The finding that matters most about our own reader

The primary recognizer scores 1.000 on its own boxes — circular, since it
produced the values — and **0.440 when the crop is padded by 0.4% of page
width**, almost all of it into abstention. PaddleOCR and Qwen3-VL lose nothing
over the same change. The pipeline depends on the detector's box being exactly
right, and that dependency is invisible in the yield numbers because the same
detector supplies both.

The same sensitivity nearly cost us the confirmer: on a crop spanning both
alleles, PP-OCRv5 contradicted the pipeline on 50.7% of the cells everything
else called stable. Per-value-box crops moved that to 97.3%.

## 5. What these numbers cannot tell you

They are yields and agreement rates between machines. Two engines agreeing can
be two engines making the same mistake, and the strata that produced several of
these figures were defined using the engines being measured.

The one instrument that changes this is a person reading: **HA-008** (the
anchored review pack, 150 documents across 15 failure strata, ~2.5 hours) and
**HA-007** (the blind golden corpus). Until then nothing here may be published
to Gold.
