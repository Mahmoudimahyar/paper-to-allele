# OCR engine benchmark on the real archive

**Measured 2026-09-01** on 220 unique original photos sampled at random from
`data/raw/ChatExport_2026-08-31` (median longest edge 520 px, p90 1280 px —
matching the corpus distribution).

**Hardware:** Ryzen 9 9900X (12C/24T), 64 GB, GTX 1070 (compute 6.1).
**Privacy:** no recognized text, caption, or image left the measuring process.
Only counts, timings, confidences and regex-hit tallies are recorded here.

## The workload

| | |
|---|---|
| original photos | 145,697 |
| **unique originals (SHA-256)** | **33,147** |
| redundant | 112,550 (**77.2%**) |

Exact-hash dedup is a **4.4× reduction** and is the single largest lever in the
pipeline. Everything below is priced against 33,147, not 145,697.

## Engine results

| engine | median ms | empty | boxes | chars | conf | HLA-value tokens | images with ≥1 HLA token | Persian chars |
|---|---|---|---|---|---|---|---|---|
| RapidOCR PP-OCR (ch/en, ONNX) | **984** | 0% | 24 | 234 | 0.75 | 505 | **47.7%** | 0 |
| PaddleOCR `lang=ar` | 6,045 | 0% | 42 | 281 | 0.66 | 719 | **61.8%** | 0 |
| Tesseract 5.4 `fas+eng` | **283** | 4% | 27 | 99 | 0.44 | 73 | 5.9% | **7,499** |

"HLA-value token" = a string matching HLA value shape (`A*02`, `B 51`,
`DRB1*15:01`). This is a *recall proxy*, not accuracy — there is no ground truth
yet, so it measures how often an engine produces something of the right shape,
not whether it is correct.

## Does a second engine help? Yes — by ~40% relative, but not the way expected

| | images yielding an HLA token |
|---|---|
| RapidOCR alone | 105 / 220 |
| **+ PaddleOCR adds** | **+42** |
| + Tesseract adds | **+0** |
| union of all three | **147 / 220 (66.8%)** |

Two findings that matter more than the headline:

**1. The engines are complementary by script, not by consensus.**

| engine | Persian | Latin |
|---|---|---|
| RapidOCR (ch/en) | **0.0%** | 100% |
| PaddleOCR `lang=ar` | **0.0%** | 100% |
| Tesseract `fas+eng` | **34.5%** | 65.5% |

Tesseract was the **only** engine that read any Persian at all, and it contributed
**zero** additional HLA values. That is not a contradiction — it is the shape of
the problem. HLA values are Latin letters and digits; patient name, lab name,
date and report metadata are Persian. **No single engine covers both.**

So the second engine is not primarily for consensus on the same token. It is for
covering a different script. Pair a Latin-capable reader for the HLA cells with a
Persian-capable reader for the metadata, and treat them as reading *different
fields*, not as voting on the same field.

**2. Where two engines did read the same values, they agreed.** On the 13 images
where both RapidOCR and Tesseract produced value tokens, **overlap was 13/13 and
total disagreement was 0** (only 1 was an exactly identical set — the rest were
subset relationships, i.e. one engine found more). Small sample, but the failure
mode so far is *missing* values, not *conflicting* ones. That matters for the
spec's consensus rule: the abstain gate will mostly be triggered by one engine
finding nothing, not by two engines disagreeing.

## Three engine issues found

**PaddleOCR does not run on this CPU out of the box.** It raises
`NotImplementedError: (Unimplemented) ConvertPirAttribute2RuntimeAttribute not
support [pir::ArrayAttribute<pir::DoubleAttribute>]` from
`onednn_instruction.cc` and returns zero text on 100% of images.
**`enable_mkldnn=False` is mandatory** on this Zen 5 machine. Setting
`FLAGS_use_mkldnn=0` does **not** work — it must be the constructor argument.

**PaddleOCR's default detector is impractical here.** It selects
`PP-OCRv5_server_det`, which did not finish 220 images in 25 minutes. Switching
to `PP-OCRv5_mobile_det` produced the 6,045 ms figure above. Even that is 6×
slower than RapidOCR.

**The Arabic recognizer may not have been exercised.** With
`lang="ar"` plus `mobile_det`, Paddle downloaded and used `PP-OCRv6_medium_rec`
rather than `arabic_PP-OCRv5_mobile_rec` (which it *did* load under the default
detector). Paddle reported **0 Persian characters**, which is consistent with a
Latin recognizer. **Its 61.8% HLA figure is therefore a fair Latin-path result,
but its Persian capability is unmeasured.** Re-run pinning
`text_recognition_model_name="arabic_PP-OCRv5_mobile_rec"` before drawing any
conclusion about Persian.

### A methodology note worth keeping

Tesseract initially returned **zero text on 100% of images at 26 ms**. That was
**my harness**, not the engine: `--tessdata-dir "path"` with quotes fails to open
the data file, while unquoted works. Verifying before concluding turned "Tesseract
is useless on this corpus" into "Tesseract reads Persian and nothing else does."

**Any future benchmark must treat a 0% result as a suspected harness bug until a
direct CLI invocation reproduces it.** This belongs in the OCR benchmark
methodology.

## Throughput on this hardware

Parallel scaling, RapidOCR, 200 images, each worker pinned to one intra-op thread:

| workers | img/s | speedup |
|---|---|---|
| 1 | 0.76 | 1.00× |
| 4 | 1.69 | 2.22× |
| **8** | **1.91** | **2.52×** |
| 12 | 1.69 | 2.23× |
| 16 | 1.45 | 1.91× |

**Throughput peaks at 8 workers and then declines.** The single-process
unrestricted run already achieves ~1.01 img/s using internal threading, so the
real gain from process parallelism is only **~1.9×**. This is a
memory-bandwidth-bound workload, not a core-count-bound one. Do not size the
pipeline on 24 threads.

### Full-corpus estimates — 33,147 unique originals

| configuration | throughput | **wall clock** |
|---|---|---|
| Tesseract only | ~7 img/s | **~1.3 h** |
| **RapidOCR only** | 1.91 img/s | **~4.8 h** |
| RapidOCR + Tesseract | — | **~6.1 h** |
| PaddleOCR only | ~0.31 img/s | **~30 h** |
| RapidOCR + PaddleOCR | — | **~35 h** |
| all three | — | **~36 h** |

Without dedup, multiply by 4.4: RapidOCR alone would be **~21 h**, all three
**~158 h**.

**Recommended configuration: RapidOCR + Tesseract, ~6 hours for a full pass.**
That buys the Latin HLA path and the Persian metadata path together, and is short
enough to iterate on overnight. PaddleOCR's +40% relative HLA coverage is real and
may be worth its 30 hours **once**, for the golden-corpus calibration run — but it
is too slow for the iterate-and-measure loop.

### Two important caveats on these numbers

1. **This is full-page OCR, which is not the production design.** The spec's
   geometry-first approach template-aligns first, then OCRs small cell crops.
   Recognition on a cropped cell is far cheaper than on a full page, but adds
   template matching and alignment. The numbers above are an **upper bound** on
   the recognition stage and a **lower bound** on the total, since alignment is
   not included.
2. **`intra_op_num_threads=1` was forced in the scaling test**, which is why the
   1-worker row (0.76 img/s) is slower than the unrestricted single-process run
   (1.01 img/s). The 8-worker figure is the one to plan against.

## What we can and cannot extract

From the sample, **66.8% of unique images yield at least one HLA-shaped token**
from some engine. The remaining third yield none. Causes, in expected order of
size, all still to be confirmed against labelled data:

- the image is not a lab report (advertisement, screenshot, ID photo, chat capture);
- the report is occluded, cropped, or photographed at an angle the detector fails on;
- text is too small at 520 px for the recognizer to detect at all;
- the HLA values are printed in a format the shape-regex does not match.

**This is a recall proxy, not accuracy.** A token of the right shape may still be
the wrong characters, and — far more dangerously — may be assigned to the wrong
locus. Nothing here measures wrong-locus false acceptance, which remains the
metric that matters most and requires the labelled golden corpus.

## Sender-side signal (from message text, no OCR)

| | |
|---|---|
| distinct senders (pseudonymised on read) | 6,175 |
| senders posting ≥1 photo | 4,419 (71.6%) |
| …with ABO in their own captions | **3,788 (85.7%)** |
| …with the word HLA in their captions | 641 (14.5%) |
| …with molecular notation in captions | 23 (0.5%) |
| …with a phone number in captions | 2,029 (45.9%) |
| senders posting ≥50 photos | **561** |
| photos from the top 10 senders | 29,970 (**20.6%** of all photos) |

Median sender: 4 messages, 2 photos — consistent with individuals posting their
own record. But **561 senders posted ≥50 photos and the top 10 alone account for
a fifth of the corpus.** Those are brokers, agents or channel admins reposting
other people's records.

**Consequence for entity resolution:** "one sender = one candidate" holds for the
long tail and fails badly for the head. The subject of a document must come from
the document and its bundle, never from the poster's identity — which the product
constitution already requires, and which this distribution now quantifies.

**Consequence for the pipeline:** 85.7% of photo-posting senders state a blood
group in text. Caption-derived ABO covers most of the population **with no OCR at
all**, and should land before the OCR work.

## Reproducing

The spike lives outside the repo (throwaway venv) so the pinned lockfile stays
honest until an engine is actually adopted. To rebuild:

```
uv venv --python 3.12 .venv
uv pip install pillow numpy opencv-python-headless rapidocr-onnxruntime pytesseract paddlepaddle paddleocr
winget install --id UB-Mannheim.TesseractOCR
# fas.traineddata from github.com/tesseract-ocr/tessdata into a local tessdata dir
```

Non-obvious flags that are required, not optional:

- `PaddleOCR(..., enable_mkldnn=False)` — otherwise zero output on this CPU
- `PaddleOCR(..., text_detection_model_name="PP-OCRv5_mobile_det")` — otherwise impractically slow
- `--tessdata-dir <path>` **unquoted** — quoted fails to open the data file


---

# Full-corpus extraction pass — 2026-09-02

`scripts/ocr_pass.py` (ADR 0006 stages 0–2) over every unique original.

| | |
|---|---|
| unique originals processed | **33,147** |
| failures | **0** |
| text boxes extracted | **2,914,800** |
| mean | 226 ms/image |
| wall clock | **~2.1 h**, single process |
| store | `data/derived/ocr_pass.sqlite`, 177 MB (gitignored) |

## The group rule is confirmed at scale

Counting only **unambiguous** locus names — `DRB1/DRB3/DRB4/DRB5/DQA1/DQB1/DPA1/DPB1`,
because a bare "A", "B" or "C" matches far too much incidental text:

| signal | images | share |
|---|---|---|
| yielded no text at all | 99 | 0.3% |
| **≥2 unambiguous loci → an HLA typing report** | **20,201** | **60.9%** |
| a value adjacent to an unambiguous locus | 19,115 | 57.7% |

The looser regex that also accepts single-letter loci reports 83.2%, which is an
overcount. **~61% is the defensible figure**: three out of five unique images in
this archive are HLA typing reports. That corroborates the channel rule that
every submitter must publish their test.

## Locus availability — this changes the V1 ranking outlook

| locus | images | share |
|---|---|---|
| DRB1 | 19,231 | 58.0% |
| DRB3 | 19,018 | 57.4% |
| **DQB1** | **16,904** | **51.0%** |
| DRB4 | 7,956 | 24.0% |
| DRB5 | 3,972 | 12.0% |
| DQA1 | 2,508 | 7.6% |
| DPB1 | 2,412 | 7.3% |
| DPA1 | 2,162 | 6.5% |

**DQB1 is present on 51% of unique images.** The earlier caption-based estimate
(0.65% of messages) badly understated it, because HLA data lives in the images,
not the captions. The `MATCHING_POLICY_V1` decision to rank DQ first is therefore
**viable on this corpus**, not aspirational — a direct correction to the concern
raised in `MVP_PLAN_REVIEW_2026-09-01.md` §5.

DRB3/4/5 appear frequently and at different rates from each other, which is
consistent with them being separate genes and supports the spec's insistence that
a `DRB3/4/5` form row is a presentation grouping, not one field.

## Persian: 0.0%, and that is expected, not a failure

The recognizer is `crnn_mobilenet_v3_small`, a **Latin-only** model — its output
alphabet cannot represent Persian at all. This pass deliberately covers the Latin
half. Persian metadata (patient, laboratory, dates) requires the separate
EasyOCR `fa` GPU pass in ADR 0006 stage 4, which has not been run yet.

**Do not read 0.0% Persian as "no Persian in the archive".** It means "this
engine cannot emit Persian".

## What this unblocks

The 20,201 multi-locus images are the stratum the 200-document golden corpus
should be sampled from — instead of from raw noise, where roughly two in five
images are not typing reports at all. Box geometry is stored in normalized
coordinates, so it is directly usable for template-family discovery and for the
median-stack/variance-map approach in `MVP_PLAN_REVIEW_2026-09-01.md` §3.5.

Still not done here, by design: **no locus is assigned to any value.** That needs
template geometry.
