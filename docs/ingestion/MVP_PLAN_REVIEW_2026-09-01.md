# MVP plan review — speed, accuracy, and three traps

**Reviewed:** 2026-09-01, before implementation begins.
**Basis:** the real archive (measured, not estimated) plus primary-source research.

**Verdict:** the plan's *safety architecture is right and should not be weakened*.
Geometry-decides-the-locus, abstain-on-ambiguity, deterministic versioned
matching, and no-LLM-as-authority are all correct and unusually well judged.

Three things change: the pipeline **order** (large speed win, no accuracy cost),
several **OCR technique choices** (evidence says the plan's instincts are right
but its defaults are wrong), and **three traps** that would each have produced a
silent clinical error.

---

## 1. What the machine and the archive actually are

Both measured on this box, not assumed.

| | |
|---|---|
| GPU | GTX 1070, 8 GB, **compute capability 6.1** |
| CPU | Ryzen 9 9900X, 12C/24T, 64 GB RAM |
| photos | 178,384 files → **47,105 unique by SHA-256** (73.6% redundant) |
| most-repeated single image | **994 copies** |
| messages | 183,897; 37% forwarded; 7% joined |
| carries a blood group (ABO) in text | **56.7%** |
| mentions HLA in text | 4.8% |
| molecular notation (`A*NN`) in text | **0.16%** |
| PRA / DSA / antibody in text | **0.02%** |
| crossmatch in text | 0.38% |

Two hardware facts decide the architecture:

- Pascal GP104 runs FP16 at **1/64** of FP32 rate.
- TensorRT requires **SM 7.5+**; 6.1 is excluded.

So PaddleOCR's High-Performance Mode — the source of its published 73.1% latency
reduction — is **unavailable here**. This is a **CPU pipeline** with the GPU as an
optional FP32 assist for small CNNs. **Bulk VLM inference over 47,105 documents is
not viable on this machine** and should not be planned for.

---

## 2. Speed: order the pipeline by cost per image

Measured per-image costs on this box:

| stage | cost |
|---|---|
| cheap key: size + 8 KB head/tail hash | 0.06 ms (17,062 files/s/core) |
| SHA-256 full file | 0.41 ms (197 MB/s) |
| **draft** decode + dHash | 0.23 ms (**4,431 img/s** at 8 workers) |
| heuristic prefilter features | 1.27 ms |
| all-pairs Hamming over the whole corpus | **22 s, once** |
| PP-OCR text **detection** | **83 ms** |
| full det + cls + rec | **389 ms** |

**Detection is ~370× more expensive than anything that should precede it.** That
ratio is the whole argument: a prefilter that removes even 10% of images pays for
itself 37 times over.

### What this means in wall-clock

At 389 ms/image, the full corpus is **~19 hours** of single-stream OCR.
Exact-hash dedup alone (measured 3.8×) takes it to **~5 hours**, and parallelism
across 12 cores brings a full pass into the **sub-hour** range before any
classification filtering. The plan already dedups before OCR — this quantifies
why that ordering is load-bearing rather than tidy.

### Concrete changes

1. **Two-stage hashing.** Cheap key `(file_size, blake2b(first 4 KB + last 4 KB))`
   first; full SHA-256 only inside colliding groups. 8.5 s vs 36 s per core.
   SHA-256 remains the *only* signal permitted to merge assets.
2. **One fused decode pass.** `im.draft("L", (32,32))` measured **1,396.8 vs
   170.9 img/s** — an 8.2× win from one line. Emit the hash thumb, a
   verification thumb, and prefilter features from a single decode. Do not decode
   three times.
3. **No ANN index.** Blocked brute-force Hamming with `np.bitwise_count` runs the
   full 145,700² upper triangle in **22 s**. FAISS, hnswlib, BK-tree and vptree
   all solve a problem that does not exist at this scale, and each would cost a
   dependency, an OSS-register entry, and an approximation error.
4. **Run text detection once** and reuse its output for three purposes: the
   is-this-a-document gate, template anchor matching, and cell OCR. Running it
   twice doubles the most expensive stage.
5. **Content-addressed cache** keyed on `(sha256, model_version,
   preprocessing_version)` so a multi-hour pass is resumable and re-running is
   genuinely idempotent, which `MVP-HIST-QA-001` already requires.

### The ordering change that matters most to the schedule

`TEST_PLAN.md` §8 gates OCR on **200 manually labelled unique documents**. That
gate is right, but it is currently positioned before classification. Sampling 200
documents from the raw corpus spends most of the human budget labelling
advertisements and screenshots.

**Run parse → dedup → prefilter → classify over the whole corpus first, then
stratify-sample the 200 from the HLA-typing stratum.** Same human effort, far
more usable labels, and the earlier stages are cheap enough (minutes) that this
costs nothing. This is a reordering, not new work, and it is the single largest
schedule improvement available.

---

## 3. Accuracy: the plan's instincts are right, its defaults are wrong

### 3.1 No generative super-resolution. Ever, in this path.

The evidence for SR improving OCR is real but collapses as the recognizer
improves. Closest analogue (Lat & Jawahar, 75 dpi documents — the same regime as
our 520 px median): Tesseract word accuracy **0.10% → 64.77% with plain bicubic
→ 85.96% with GAN-SR**, but for a strong recognizer ABBYY moved **96.95 → 96.95 →
97.88** characters. Plain interpolation captures nearly all the recoverable
signal; SR adds under one character point *by generating pixels that were never
measured*.

Worse, `TextSR` conditions its diffusion on the OCR's own guess — with a poor OCR
it paints a confident, plausible, **wrong** glyph.

**Do:** upscale each cell crop with Lanczos/bicubic so text height lands at
**32–48 px** (PP-OCRv5 resizes every line to height 48 internally anyway —
`d2s_train_image_shape: [3, 48, 320]` — so doing that resize well, once, outside
the model is the entire mechanism). Then a **mild Gaussian low-pass**. Do **not**
unsharp-mask: at 520 px the high frequencies are mostly JPEG aliasing, and a
measured 2× down-then-up round trip *improved* Tesseract.

**Add to `OCR_SPEC.md` as a hard rule:** *no pixel may be synthesized by a
generative model in the path that produces a proposed medical value.*
Interpolation is reversible and auditable; generation is not.

### 3.2 Preprocessing is per-branch, and the neural default is OFF

PaddleOCR's own definition of preprocessing for PP-OCRv5 contains **no
binarization and no contrast enhancement** — only orientation classification and
unwarping. PP-StructureV3 runs "PP-OCRv5 with preprocessing disabled." Its
detector was trained with blur and geometric augmentation, so the degradations
CLAHE would remove are already in its training distribution. A controlled
experiment on a modern neural engine found **no preprocessing variant beat the
baseline**, while adding 22–26% latency.

- **Neural branches** (PaddleOCR, any VLM): geometric normalization only —
  deskew, rectify, crop. Keep 3-channel colour and the antialiasing gradients,
  which at 520 px are where the remaining stroke signal lives.
- **Tesseract branch only**: keep CLAHE + adaptive threshold, because Tesseract
  binarizes with Otsu regardless and its own docs concede that is suboptimal on
  uneven backgrounds.

Settle it empirically: add a `{none, geometric, geometric+CLAHE,
geometric+binarize} × {engine}` ablation to the 200-document gate. Eight runs.

### 3.3 Do not model-shop. Fine-tune, with a restricted alphabet.

Best available Persian numbers (MORE, ICML 2026, real documents, NED): Qwen3-VL-2B
89.95, Qwen2.5-VL-3B 84.30, PaddleOCR-VL 80.75, dots.ocr 78.87. Spread between
best and worst ≈ **11 points**.

Spread between off-the-shelf and fine-tuned on Arabic script (QARI-OCR):
CER **0.436 → 0.061**, a **7× reduction**.

Domain adaptation is the dominant lever; model selection is a rounding error next
to it. Budget accordingly.

For an HLA cell, restrict the character dictionary to roughly
`{0-9, A, B, C, D, R, Q, P, W, *, :, /, -, space}`. That deletes ~6,000 Arabic
output classes — i.e. ~6,000 distinct ways to be wrong — at no cost.

**Generalization is the matching risk:** the same fine-tuned model degraded to
CER 0.156–0.230 on an out-of-distribution font set. The golden corpus must
include lab families the model was *not* tuned on.

### 3.4 A VLM cannot be the authority, and the plan is right to say so

Two independent reasons, both now evidenced:

- VLM alignment layers "introduce information bottlenecks… image details such as
  small character recognition are discarded," and abstention research finds VLMs
  "rely on miscalibrated output probabilities." There is no usable per-character
  posterior — which is exactly what the abstain gate needs.
- Table structure is the worst task in the benchmark: `dots.ocr` scores **94.45
  on text but 39.81 on tables**; best camera-captured TEDS is 78.56. A full-page
  VLM read of an HLA table will scramble row/column association a large fraction
  of the time *even when the characters are correct*.

This is direct quantitative support for the existing geometry-first rule. Keep it.

### 3.5 Template identification: shortlist, then *prove* it

**Do not** use a classifier alone. A classifier returns "Yekta" with 0.97 softmax
on a form rotated 30° with the header cut off, and the fixed boxes then land on
the wrong loci — the exact silent failure the spec forbids.

- **Stage 1 (cheap shortlist):** DINOv2 ViT-S/14 embedding, k-NN against labelled
  exemplars, take **top-3, never top-1**. DINOv2 over CLIP because this is
  instance-level "same printed form" similarity; CLIP embeds *meaning* and will
  happily place two different lab forms together because both "are a medical
  document." Apache-2.0, code and weights.
- **Stage 2 (authoritative):** XFeat sparse matching + `cv2.findHomography(…,
  USAC_MAGSAC)`. **The homography is the identification evidence.** Accept only
  on inlier count, inlier spatial distribution, and per-anchor reprojection
  residual. Two candidates passing, or none, → `REVIEW_REQUIRED`. XFeat is
  Apache-2.0 and its design point is VGA CPU inference — essentially our median
  image. A form on a table is planar, so the homography is exact, not approximate.
- **No learned dewarpers** (DocTr++/DocGeoNet/DewarpNet/UVDoc): a dense grid warp
  has no error certificate — when wrong it *translates cells* rather than failing
  visibly — and several are non-commercial licensed.

**One idea worth more than any model choice:** build each template's reference by
**median-stacking N mutually-aligned samples**. The stack is a high-SNR image of
the form's printed furniture, and the **per-pixel variance map separates printed
furniture (low variance) from filled-in data (high variance)** — so the data cells
discover themselves. Template authoring drops from hours of eyeballing
coordinates to minutes, and the boxes become objective and reproducible.

---

## 4. Three traps

Each of these would have produced a silent clinical error with a fully green
test suite behind it.

### TRAP 1 — Perceptual hashing merges different patients

`DEDUPE-002` plans perceptual/crop duplicate clustering. Measured null
distributions for *unrelated* pairs:

| image kind | dHash-64 mean | collision rate at t≤6 |
|---|---|---|
| ordinary photos | 32.0 (sd 4.3, min 12) | **0 false pairs at t≤10** |
| **same-template documents** | **6.4 (sd 3.0, min 0)** | **53.3%** |

pHash is worse: 75.4% at t≤6. Two different patients' Yekta forms are
near-identical to a global perceptual hash, because the form furniture dominates
the image.

**A global perceptual hash must never merge documents.** Use it only to generate
*candidates*, then verify — by homography inlier geometry, or by comparing only
the high-variance data regions identified by the template's variance map. Never
use CNN embeddings here: they make this *worse*, since two patients' forms are
semantically identical.

This is the same hazard as the existing "HLA similarity alone never merges
people" invariant, arriving by a different route. `DEDUPE-002`'s spec needs the
threshold **and the verification step** written into it before implementation.

### TRAP 2 — py-ard silently mutates your medical reference data

`pyard.init()` defaults `imgt_version` to **`"Latest"`**. Calling it bare means
the HLA reference database changes underneath you every quarter, and an
accept/abstain decision recorded today cannot be reproduced. The default SQLite
location is **`$TMPDIR/pyard-$USER/`**, which the docs themselves note "may be
removed upon computer restart."

```python
ard = pyard.init('3650', data_dir=<repo-managed path>,
                 load_mac=False, config={'strict': True})
```

Pin `py-ard==2.4.0`; build once with `pyard-import --imgt-version 3.65.0
--data-dir <path> --skip-mac`; record `ard.get_db_version()` in **every**
extraction record. `load_mac=False` because NMDP MAC codes are a US
bone-marrow-registry convention that Iranian solid-organ forms will not print.

`HLA_VALIDATION_SPEC.md` already says to pin IPD-IMGT/HLA 3.65 — this is the
mechanism that makes that real rather than aspirational.

### TRAP 3 — Serology is a third category, and the mapping is directional

This is the most consequential finding for correctness.

**Serologic typing is not "low-resolution DNA typing."** EFI v9.0 defines low
resolution as a *DNA-based* result at first-field level. The schema needs
`SEROLOGIC | ALLELE_GROUP_1F | ALLELE_2F | ALLELE_3F_PLUS`, **stored per locus**,
because one Iranian form routinely mixes them (serologic A/B, molecular DRB1).

**The mapping runs molecular → serologic ONLY, never the reverse.** Compare in
serology space when either side is serologic. IPD-IMGT/HLA says its own
`rel_dna_ser` file is "produced solely as a tool for validation… and is not
produced to infer the serological typing."

**Matching equivalence is not "broad absorbs splits."** It is a curated table with
asymmetries — OPTN: a candidate typed B70 matches only donors typed B70; B71 and
B72 are *mismatched*. And the unacceptable-antigen relation runs the **opposite
way**: candidate unacceptable B70 excludes donors typed B70, B71, B72, 15:03,
15:10, 15:18. **Exclusion expands; matching contracts.** These must be two
separate, separately tested lookup tables. Conflating them is the single most
dangerous simplification available here.

`py-ard` gives us the tools: `is_serology`, `find_broad_splits`,
`find_associated_antigen`, `v2_to_v3`, and a validator whose own tests assert
`DR7 valid / DR99 invalid / A10 valid / A101 invalid`. Note also that Iranian
forms often print **V2 notation** (`A*0201`); `is_v2()`/`v2_to_v3()` handle it,
but the conversion must be a recorded, reversible step — never a silent regex.

---

## 5. What the data says about the matching design

The ranking tuple leads with immunologic blockers, then crossmatch, then DQ. In
this archive:

- antibody/PRA/DSA appears in **0.02%** of messages,
- crossmatch in **0.38%**,
- molecular notation in **0.16%**.

**Ranking keys 1 and 2 will be constant across effectively the whole corpus.**
They are correct as *safety gates* and must stay. But they will do no ranking
work, so ordering effectively begins at DQ — and DQ availability depends entirely
on OCR of the images.

Meanwhile **ABO appears in 56.7% of messages, in text**. That is the highest-yield
signal in the archive and it needs no OCR at all.

**Recommendation:** treat caption-derived ABO as a first-class deliverable that
lands *before* OCR. It makes Gate A real for a majority of records, and gives a
useful matching dataset while OCR is still being calibrated.

### Not defensible, do not build

- Eplet / molecular-mismatch / PIRCHE-style scores from serologic input. Measured
  (Fidler, 264 pairs): **16% of pairs differ by >5 eplet mismatches** with
  serologic typing versus **2%** with 2-digit molecular. The authors' conclusion
  is that serologic eplet mismatch is not an acceptable methodology.
- Inferring C, DQA1, DQB1 or DPB1 by linkage disequilibrium from A/B/DR.
- Imputing high-resolution types. Best recent evidence is 87%/79% concordance on
  a **non-Iranian** cohort; applying a foreign haplotype panel to 11 distinct
  Iranian subpopulations would be worse and we could not measure how much worse.
- The word **"compatible"** anywhere in output.

### Two additions to the plan

**(a) A third forbidden inference.** The spec forbids full-page-OCR-then-regex
locus guessing, and forbids high-res-from-low-res. Add: *serologic antigens may
not be expanded to alleles, and no locus may be emitted that was not physically
present as a template cell on the source document.* Absence of a cell produces
`UNKNOWN`, never an inferred locus.

**(b) Extend the 200-document gate to the matching layer.** The current target
(≥99.5% critical-field precision, zero wrong-locus false acceptance) constrains
*extraction only*. A perfectly extracted `B5` scored against `B51` by a naive
expander is a clinical error sitting behind a 100%-accurate OCR pipeline. Add a
golden set of donor/recipient **pairs** with hand-counted expected mismatch
results, covering at minimum: broad-vs-split (B5 vs B51), a single-antigen locus
(homozygosity presumption), a locus missing on one side, a mixed
serologic/molecular pair, and a B70/B71 pair. **Test the relation, not just the
characters.**

---

## 6. Recommended work-queue changes

| Change | Why |
|---|---|
| Add `CLASSIFY-001` before `OCR-BENCH-001` in the critical path | Stratified sampling makes the 200 labels 5–10× more useful |
| Add an explicit `ABO-TEXT-001` task | 56.7% coverage, no OCR needed, makes Gate A real early |
| Rewrite `DEDUPE-002` spec with threshold **and** verification | As specified it would merge different patients (Trap 1) |
| Add a pipeline-orchestration/resume task | Content-addressed cache; `MVP-HIST-QA-001` assumes it exists |
| Add template-authoring task using median-stack + variance map | Turns hours of coordinate-eyeballing into minutes |
| Extend `MATCH-EVAL-001` to include the golden **pair** set | Extraction accuracy does not imply relation correctness |

## 7. Needs a human decision

- **HA-003** (already open): the pixel threshold for mandatory review.
- **Iranian transplant practice.** Everything above is OPTN (US), EFI/Eurotransplant
  (EU) and WHO nomenclature. **No Iranian histocompatibility standard was
  consulted.** If Iranian practice differs on which loci are typed or how
  mismatches are counted, it outranks all of it and must be resolved before the
  matching spec is frozen. This is the largest open question in the project.
- Whether to vendor the OPTN equivalence tables. They are revised annually and may
  be PDF-only; a transcription error there is a silent clinical error, so budget
  double-entry verification.

## 8. What not to change

The safety architecture. Geometry decides the locus. Abstention is a valid
outcome. Missing is `UNKNOWN`, never zero. Matching is deterministic, versioned,
and cannot read compensation. No LLM makes a final finding. Every one of those
survived contact with both the evidence and the data, and several are now backed
by numbers they did not have before.
