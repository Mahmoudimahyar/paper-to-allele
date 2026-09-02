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


---

# Phase 2 — template discovery, golden sampling, Persian pass (2026-09-02)

## A correction that changes the resolution picture

I previously reported the archive's median longest edge as **520 px**. That is
true of a random sample of **all 145,697 originals**, but it is **not** true of
the 33,147 **unique** originals that are actually processed:

| percentile | longest edge, UNIQUE originals |
|---|---|
| p10 | 520 px |
| p25 | 520 px |
| **p50** | **1,278 px** |
| p75 | 1,280 px |
| p90 | 1,280 px |

Only **29.7%** of unique images are ≤640 px; **64.0%** exceed 900 px.

The heavily-duplicated images — broker reposts, recompressed on each hop — are
disproportionately low resolution, and exact-hash dedup removes them. The unique
set is bimodal (a ~520 px cluster and a ~1,280 px cluster), not uniformly poor.
**The OCR target is in materially better shape than the raw corpus implied.**

This also means the 220-image engine benchmark above was run on a
lower-resolution sample than production, because it sampled from all originals
and deduped afterwards. Its relative ordering stands; its absolute difficulty is
pessimistic.

## Template family discovery

`scripts/template_discovery.py`. Signature = the normalized position of each
**unambiguous** locus label; group by which loci a form reports; cluster by
position; then **verify against layout-occupancy coherence, a signal the
clustering never saw**.

| | |
|---|---|
| documents with ≥2 located loci | 20,057 |
| distinct locus-presence patterns | 160 |
| candidate families | 59 |
| **VERIFIED single templates** | **11**, covering 2,479 documents (after the label-only fix below) |

The dominant presence pattern is `DRB1+DRB3+DQB1` (25.3%), then
`DRB1+DRB3+DRB4+DQB1` (14.3%).

The verification step earns its place: of the eight largest clusters in the
biggest group, two were mixtures (coherence lift +0.016 and −0.060) despite
having 365 and 182 documents. **Hand-authoring cell boxes against those would
have mapped cells to the wrong locus on part of the family.** Only the 5
verified families are eligible for registry authoring.

## Template discovery is strongly resolution-biased

| band | share of corpus | share of verified-family docs | reaches a verified template |
|---|---|---|---|
| ≤560 px | 29.2% | **0.3%** | **0.05%** |
| 561–900 px | 6.9% | 4.8% | 3.30% |
| >900 px | 64.0% | 94.9% | 7.03% |

A **~140× gap**. Low-resolution documents rarely produce enough clean locus
labels to cluster, so they are nearly absent from the verified families. Left
uncorrected, the golden corpus would certify the pipeline on the easy half of the
archive and say nothing about the 9,666 low-resolution documents — which is
exactly where the mandatory-review policy must hold. `golden_sample.py` therefore
carries a dedicated `low_res_report` stratum.

## Golden sample

`scripts/golden_sample.py`, 200 documents:

| stratum | docs | purpose |
|---|---|---|
| verified_template | 120 (61%) | certify each template's cell mapping; **equal** allocation across all 5 |
| mixture_family | 40 (20%) | where matching should abstain |
| low_res_report | 18 (9%) | the resolution tail the bias above would otherwise hide |
| non_report | 20 (10%) | the only way to measure false acceptance |

**The metric unit is the CELL, not the document.** A report carries several locus
cells, so 200 documents is roughly 800 cells. By the rule of three, zero failures
in n gives a 95% upper bound of 3/n, so ~800 cells bounds the error at ~0.375%,
consistent with a ≥99.5% precision claim. **200 documents treated as 200
observations would only bound it at 1.5% and could not support the claim.**
Record cells labelled, not documents.

## Persian pass

`scripts/persian_pass.py`, EasyOCR `fa+en` on GPU, over the 20,201 report
documents. Two measured decisions:

- **It does its own detection.** Feeding it the stored Latin boxes is **1.4×
  slower** (2,386 vs 1,688 ms) despite yielding 8.5% more Persian. Those boxes
  are word-level from a Latin detector; Persian is cursive and line-level regions
  are both cheaper and more faithful to connected script.
- **Downscaling is not a lever.** At a 640 px cap it is only 21% faster but loses
  **26%** of Persian characters. EasyOCR's cost tracks the number of detected
  text regions, not the input size. Rejected.

Measured ~2,000–2,700 ms/image on the unique set (higher than the 686 ms seen
earlier, because the unique set is ~1,280 px rather than ~520 px). Full pass
≈ 12–15 h, resumable, GPU-bound so it leaves the CPU free.


## CORRECTION (2026-09-02): the locus regex matched values, not labels

`DRB1` also matches the `DRB1` inside `DRB1*11`. Measured over 33,048
documents this inflates apparent presence by **5.18x for DRB1** and **5.15x for
DQB1**.

Two different consequences, and they must not be conflated:

- **The corpus claim survives.** "Does this archive contain DQ typing?" is
  legitimately answered by a value token, so *DQ data is present on about half of
  unique images* still holds.
- **The template signature did not survive.** It placed the "locus position"
  wherever a patient-specific value fell rather than where the form prints its
  label. Corrected to `^(?:HLA[-\s]?)?<LOCUS>$`; the family set changed from 5
  covering 1,571 documents to 11 covering 2,479. **Do not quote the earlier
  figures.**

See ADR 0007, which also retires the absolute-cell-box registry design: within one
otherwise-clean family the `DRB4` label sits in two different columns and layout
geometry provably cannot separate the variants, so an absolute box would bind the
wrong locus for ~40% of members.

Also measured: **cluster sizes overstate template prevalence by ~2x** (16,571
documents with >=4 allele tokens collapse to 7,764 distinct fingerprints; 71.7%
share one). Report families by effective sample size.


## The anchor-purity gate (2026-09-02) — and what it cost

ADR 0007 argued that layout coherence is necessary but not sufficient. Adding the
**anchor-purity** test — does each locus label sit in ONE modal position across a
family's members? — changes the answer substantially:

| gate | verified families | documents |
|---|---|---|
| coherence + tight geometry | 11 | 2,479 |
| **+ anchor purity (modal share >= 0.70)** | **5** | **613** |

The families it rejected are exactly the predicted failure:

| family | docs | pos sd | coherence lift | modal share | weakest locus |
|---|---|---|---|---|---|
| `DRB1+DRB3+DQB1#9` | 606 | 0.0205 | **+0.179** | **0.60** | DRB1 |
| `DRB1+DRB3+DRB4+DQB1#2` | 528 | 0.0605 | +0.022 | **0.22** | **DRB4** |
| `DRB1+DRB3+DQB1#3` | 215 | 0.0841 | −0.042 | **0.14** | DRB3 |

`DRB1+DRB3+DQB1#9` has excellent geometry (sd 0.0205) and a strong coherence lift
(+0.179) — **it would have passed the old gate** — yet its `DRB1` label occupies
one position in only 60% of members. An absolute cell box there binds the wrong
locus for the other 40%.

`DRB4` recurs as the weakest anchor across several families, which is precisely
the two-column variant ADR 0007 describes.

**Only 613 documents currently sit in families where every locus label reliably
occupies one position.** That is a much smaller base than the earlier numbers
implied, and it is the honest one. It also strengthens the case for the
relation-based registry: per-document anchoring does not need a family to be
positionally uniform at all.


## Near-duplicate collapse — the golden corpus is smaller than it looked

These images are already SHA-256 unique, so a shared allele fingerprint means
NEAR duplication: the same report rephotographed or recompressed.

| | |
|---|---|
| documents with >=4 allele tokens | 17,830 |
| **distinct allele fingerprints** | **9,738** |
| documents sharing a fingerprint | 11,207 (**62.9%**) |
| largest repeat group | 81 documents |

Per family it is worse than the corpus average. Two of the five verified
families are near-duplicate collapses:

| family | documents | distinct fingerprints | ratio |
|---|---|---|---|
| `DRB1+DRB3+DRB5+DQB1#4` | 304 | 154 | 0.51 |
| `DRB1+DRB3+DQB1#11` | 83 | **3** | **0.04** |
| `DRB1+DRB3+DQB1#6` | 62 | **5** | **0.08** |

A family of 83 documents that is really 3 patients' reports photographed
repeatedly is **3 independent observations, not 83**. Sampling it without
collapsing would draw the same report many times and count it as independent
evidence, inflating every confidence bound computed from the golden corpus.

`golden_sample.py` now collapses to one document per allele fingerprint. The
effect is visible and material: the verified-template stratum fell from 120
documents to **80**, because only 80 independent ones exist. The shortfall is
made up from the non-report stratum, which is where false acceptance is measured
anyway.

**This changes the power calculation.** The earlier "~800 cells" figure assumed
200 independent documents. With collapse the sample is ~199 documents but fewer
independent typing reports, so the cell count backing a >= 99.5% precision claim
should be recomputed from the labelled set rather than assumed.

### A bug worth recording

The first implementation of this collapse silently did nothing. Writing the
pattern through a non-raw Python string turned `` into a literal **backspace
character (0x08)**, which is invisible in an editor, passes lint, and makes the
regex match nothing. It was caught only by checking that the fingerprint count
matched an earlier standalone measurement. **Verify that a new filter actually
fires, rather than trusting that it ran.**


---

# Persian pass complete (2026-09-02) — and an honest accounting

| | |
|---|---|
| reports processed | **20,201** |
| failures | **0** |
| Persian characters | **3,842,648** |
| mean | 1,834 ms/image |
| wall clock | **~10.2 h**, GPU |
| documents with no Persian at all | 147 (0.7%) |

Metadata field cues present, as a share of the 20,201 reports:

| cue | documents | share |
|---|---|---|
| name | 8,875 | 43.9% |
| doctor | 6,831 | 33.8% |
| laboratory | 5,900 | 29.2% |
| date | 5,165 | 25.6% |
| sample | 358 | 1.8% |
| national ID | 304 | 1.5% |

## What the Persian pass actually bought

Comparing the two passes per document, over the same 20,201 reports:

| signal | Latin pass | Persian pass | union | **gain from Persian** |
|---|---|---|---|---|
| laboratory marker | 14,052 | 6,563 | 14,057 | **+5** |
| date pattern | 12,422 | — | 12,782 | +360 |
| Persian name cue | 0 | 8,875 | 8,875 | **+8,875** |

**The Persian pass bought exactly one thing: patient name fields.** Laboratory
names are printed in Latin, so the Latin pass already had them — Persian added
**five** documents. Dates gained 360. Everything else was already there.

Ten GPU-hours for one field. That is worth stating plainly, and it is worth
weighing before repeating this on future archives: if names are not needed, the
Persian pass is close to unnecessary.

## A governance question this raises

The one field the Persian pass uniquely unlocks — the patient name — is
simultaneously:

- the **highest-PII** field in the archive,
- **useful for entity resolution** (linking one person's repeated posts), and
- **irrelevant to HLA matching**, which needs no name at all.

`PRODUCT_CONSTITUTION.md` §4 keeps direct identifiers hidden until a connection is
mutually approved, and historical records stay unclaimed. Extracting 8,875 names
into a derived store is defensible for deduplication, but it is a deliberate
increase in the amount of identifiable data we hold, and it should be an explicit
decision rather than a side effect of running an OCR pass.

**Recommendation:** store the name only as a salted hash for entity-resolution
matching, and keep the plaintext out of the derived store unless a reviewer
workflow genuinely needs to read it. That preserves the dedup value at a fraction
of the exposure. Raised as a human decision, not applied unilaterally.


---

# Anchor-based locus resolution (ADR 0007) — measured on the corpus

> **SUPERSEDED 2026-09-02 — do not quote the rates below.** A shape audit showed
> that under the `below` rule the resolver was binding the *next row's locus
> label* as the value (DRB1: 185 value-shaped vs 988 label-shaped bindings;
> DPA1/DPB1: zero value-shaped). "The layout is columnar" was wrong: the form is
> a vertical stack of row labels with values to the right, and the recognizer
> reads the trailing `1` of labels as `I`, which hid most anchors. The 33,048
> denominator also includes 9,581 thumbnail copies (KI-009). Corrected
> measurements and the fix plan: `ACCURACY_REVIEW_AND_PLAN_2026-09-02.md`
> (§2.2) and KI-010. The section is kept as the record of what was tried.


`src/kidneymatch/ocr/anchors.py`. The `scripts/resolve_loci.py` that drove
this section was deleted on 2026-09-02: it passed its row tolerance into the
overlap parameter, still defaulted to the retired `below` direction, and read
thumbnail rows, so it measured nothing. `scripts/extract_facts.py` replaces it.

## The layout is columnar, not row-based

The first rule assumed the value sits to the RIGHT of its label. Measured over
33,048 documents that resolves almost nothing, and the diagnostic said why: for a
document with exactly one `DRB1` anchor, the nearest box to its right sits a
**median of 19.5 label-heights away vertically** — it is not on the same row at
all.

Switching the rule to `below` is **4-5x better**:

| direction | row tol | max gap | resolve rate |
|---|---|---|---|
| right | 0.6 | 2.5 | 0.7% |
| right | 0.6 | 6.0 | 1.4% |
| **below** | **0.6** | **2.5** | **3.2%** |
| below | 3.0 | 6.0 | 1.9% |

Loosening the tolerances makes it **worse**, not better: more candidates trip the
`max_values` guard and the resolver abstains. The constraint was never tolerance.

## Resolve rate among documents that actually carry the anchor

The corpus-wide rate is bounded by how often a locus label is readable at all, so
the meaningful denominator is documents with exactly one anchor:

| locus | docs with one anchor | resolved | rate |
|---|---|---|---|
| **DPA1** | 2,042 | 899 | **44.0%** |
| **DPB1** | 2,254 | 947 | **42.0%** |
| **DQB1** | 3,164 | 1,175 | **37.1%** |
| **DRB1** | 3,560 | 1,199 | **33.7%** |
| DQA1 | 1,674 | 103 | 6.2% |
| DRB4 | 5,659 | 227 | 4.0% |
| DRB3 | 8,561 | 324 | 3.8% |
| DRB5 | 2,698 | 49 | 1.8% |

**The design works for the standalone loci and fails for DRB3/4/5.** That split is
not a surprise: `HLA_VALIDATION_SPEC.md` section 7 says a form row labelled
`DRB3/4/5` is a presentation grouping, not one gene, and those three loci are
exactly the ones printed that way. They need a dedicated combined-header anchor
type that binds each of the three genes separately — binding one value to the
grouped label would assign the same allele to three genes.

## What this establishes, and what it does not

It establishes that per-document anchoring is viable: a third to nearly a half of
anchored documents resolve under a single crude global rule, with everything else
abstaining rather than guessing. A per-family rule — which is what the registry is
for — should do better than one global rule, and DRB3/4/5 needs its own handling.

It establishes nothing about **correctness**. These are resolution rates, not
accuracy: no labelled data has been compared yet. The golden corpus is what turns
"the resolver bound a value" into "the resolver bound the RIGHT value", and until
then the wrong-locus false-acceptance rate — the metric that actually matters —
remains unmeasured.
