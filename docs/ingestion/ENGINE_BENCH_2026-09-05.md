# Five recognizers against the reviewer's labels — 2026-09-05

The 2026-09-03 survey (`OCR_MODEL_SURVEY_2026-09-03.md`) ranked sixteen engines
by agreement with a *trusted set* — cells the pipeline and Tesseract already
agreed on. That measures consensus, not truth, and the survey said so. This
measures truth: the reviewer has now labelled cells by hand, and the engines
are scored against what a person read off the page.

## The test set, and what it is not

67 cells, every one a labelled `VALUE` with two alleles, from the 187 the
reviewer labelled across two exports; 134 crops, one per stored value box, cut
by `ocr/crops.py` with the `CONFIRMER_PADDED` profile and levelled on tilted
pages — the crop `confirm_pass.py` shows an engine, so what is compared is the
READING, not the framing. 55 HIGH quality band, 12 LOW.

Four labelled value cells are missing from it because the pipeline stored no
box for them, and two of the 67 have only one box for two printed alleles.

**This is not an accuracy for the product.** The labels are anchored (the
reviewer saw the pipeline's proposal beside the crop), the cells come from the
review pack's failure strata, and the crops come from our own detector — an
allele the detector never boxed is invisible to every engine here. KI-012
stands: the blind golden corpus (HA-007) remains the instrument for any
published bound.

Every engine's text goes through the same reader (`ocr/confirm._read`), so no
engine is favoured by our tolerance for its formatting. Per cell the engine's
first fields are compared as a set with the human's alleles.

## Result

| engine | exact | rate | partial | wrong | silent | ms/crop |
|---|---:|---:|---:|---:|---:|---:|
| **PP-OCRv6-medium-rec** | **65** | **97.0%** | 2 | 0 | 0 | 25.0 |
| *the pipeline, as it ships* | *57* | *85.1%* | *2* | *1* | *7* | — |
| PP-OCRv5-server-rec | 55 | 82.1% | 10 | 1 | 1 | 31.0 |
| Qwen3-VL-4B Q4_K_M (CPU) | 52 | 77.6% | 13 | 0 | 2 | 475.2 |
| PP-OCRv5-mobile-rec | 51 | 76.1% | 11 | 1 | 4 | 14.3 |
| PP-OCRv5-en-mobile-rec *(the shipped confirmer)* | 50 | 74.6% | 16 | 0 | 1 | 11.5 |
| onnxtr-parseq | 37 | 55.2% | 16 | 2 | 12 | 10.2 |
| Tesseract 5 psm7 | 32 | 47.8% | 20 | 0 | 15 | 8.5 |
| onnxtr-crnn_mobilenet_v3_small *(the pipeline's primary)* | 14 | 20.9% | 15 | 6 | 32 | 0.7 |

`exact` = both alleles right; `partial` = a subset, nothing wrong; `wrong` = at
least one field the human did not write; `silent` = nothing readable.

**PP-OCRv6-medium-rec's two non-exact cells are the two cells with only one
stored box.** It read that box correctly in both. On every cell where the
geometry gave it both alleles it was **65 of 65**, and it was never wrong and
never silent — including 12 of 12 on the LOW band, where the shipped confirmer
gets 9 and Tesseract 2.

## What that says

1. **The confirmer is a generation behind.** `en_PP-OCRv5_mobile_rec` was
   chosen on 2026-09-03 as the best of sixteen; PP-OCRv6 was listed there as an
   untested A/B candidate and never run. On labelled truth it reads 15 more
   cells of 67, for 13.5 ms more per crop (about 20 minutes over the corpus).
2. **The primary recognizer is the floor, not the ceiling.** onnxtr's
   `crnn_mobilenet_v3_small` reads 14 of 67 alone. What ships reads 57 —
   the gap is the geometry, the glyph repairs, the constrained decode, the
   second engine and the promotion rule, not the recognizer.
3. **The VLM is not the answer here.** Qwen3-VL-4B reads 52 at 475 ms/crop —
   19× slower than PP-OCRv6 and 13 cells worse. Its strength on the earlier
   survey was the *hard* stratum measured by consensus; against labels on real
   cells it trails a 25 ms recognizer.
4. **Two engines agreeing were never wrong.** Across every pair of the top
   four, agreement on a non-empty answer was exact or incomplete — never a
   shared wrong value (PP-OCRv6 + PP-OCRv5-server: 55 exact, 2 incomplete, 0
   wrong). That is the property `confirm_pass.py`'s CONFIRMED verdict rests on,
   measured for the first time against truth rather than against consensus.
5. **The pipeline's one WRONG cell** is a cell no engine here reads correctly
   either; its 7 silences are cells it refused on purpose (a gate the engines
   do not run).

## What to do with it

- Add PP-OCRv6-medium-rec to `confirm_pass.py --engine` (done: `ppocrv6`), and
  run it over the corpus under its own `confirmer_version`. It replaces
  nothing: every verdict is stored per engine, and a cell may carry three.
- Then re-measure the promotion rule with v6 as the second reader. 44% of the
  decode's proposals were contradicted by PP-OCRv5; if v6 contradicts fewer,
  the promotion gate gets more cells at the same standard of evidence.
- Do not make v6 the PRIMARY recognizer on this evidence: it read 134 crops the
  primary's detector found. What a v6 *detector* would find is a separate
  measurement (`ocr_pass` is the detector; E9 in the research record).
- Do not restate 97.0% as an accuracy. It is 67 anchored cells on our own
  crops.

## What it did to the corpus

PP-OCRv6 then read all 57,002 resolved cells and the decode's proposals, under
its own `confirmer_version` (it replaces nothing; a cell may carry three
engines' verdicts).

| | PP-OCRv5-en-mobile | **PP-OCRv6-medium** | Tesseract 5 |
|---|---:|---:|---:|
| confirmed | 90.0% | **96.9%** | 44.5% |
| contradicted | 7.4% | **2.7%** | 14.4% |
| no opinion | 2.6% | **0.4%** | 41.1% |

Head to head on the same cells, v6 turns **3,497** of v5's contradictions and
**1,208** of its silences into confirmations, and contradicts 707 cells v5
confirmed. On the labelled cells the direction is unambiguous: of 57 cells
where the pipeline's value matches the human, v5 raised **12 false alarms**
and v6 raised **none**; on the 3 where the pipeline is wrong, both confirmed 2
and contradicted 1. So v6 is dramatically quieter without being measurably
blinder — though 3 wrong cells is far too few to say it catches errors as
well, and that is what more labels would settle.

**The promotion gate now runs on it** (`promote_proposals.py`, default
`--confirmer ppocrv6/medium-rec@proposal`), and gained a rule the swap made
necessary: v6 **contradicts 57 of the 760 cells v5 had licensed**. A fact
built from two engines agreeing is withdrawn when a reader at least as good as
the licensing one disagrees (`ENGINE_RANK`, this table); a weaker one
disagreeing is the review budget, as for any other resolved cell, not a reason
to withdraw a fact. Net: **961 promoted** (was 760), 57 withdrawn, and a
withdrawn cell is promotable again if the disagreement lifts.

## Reproducing it

The harness is in the session scratchpad (crops are PHI and never leave it):
`build_crops.py` cuts the crop set from the labels and the stored boxes,
`run_engines.py` runs the local recognizers, `run_qwen.py` drives llama.cpp on
127.0.0.1, `analyse.py` prints the tables above. Counts only; no crop content,
allele value or document id is printed at any point.
