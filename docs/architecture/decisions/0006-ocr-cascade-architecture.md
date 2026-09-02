# ADR 0006 — OCR cascade: shared detection, cheap voters, syntax gate, escalate abstentions

**Status:** ACCEPTED (2026-09-01)
**Supersedes:** the engine ordering in `OCR_SPEC.md` §6 (the staged cascade is kept; the engines and their order change)

## Context

Measured on the real archive and this hardware (GTX 1070 sm_61, Ryzen 9 9900X):

| engine (full page) | median | HLA recall | Persian |
|---|---|---|---|
| **OnnxTR** fast_base + crnn_mobilenet_v3_small | **217 ms** | — | no |
| RapidOCR PP-OCR (CPU) | 984 ms | 47.7% | no |
| EasyOCR fa+en (**GPU**) | 686 ms | 5.9% | **19,619 chars — best** |
| EasyOCR en (GPU) | 256 ms | — | no |
| Tesseract fas+eng | 283 ms | 5.9% | 7,499 chars |
| PaddleOCR lang=ar (CPU) | 6,045 ms | **61.8%** | no |

Two measurements dominate every other consideration:

1. **Detection is 86% of the cost** — 185.6 ms of the 216.9 ms total.
   Recognition is **0.44 ms per crop**.
2. **Process parallelism makes OnnxTR slower**, because ONNX already threads
   internally: 4.36 img/s at 1 worker, 3.72 at 6, 3.48 at 16.

## Decision

### 1. One detection pass per unique image; every recognizer shares its boxes

Detection is the expensive stage and its output is engine-independent. Running it
once and reusing the crops makes a *second and third recognizer nearly free*
(0.44 ms/crop). This inverts the usual cost intuition and is the reason a
multi-engine design is affordable at all.

### 2. Run OCR single-process, not in a worker pool

Measured: parallelism is a net loss. Let ONNX Runtime use all cores internally.

### 3. Voting is by UNANIMITY across INDEPENDENT architectures — never majority

This is a correction to the obvious design. Measured on synthetic HLA cells:

| gate | false-accept |
|---|---|
| single engine | 4.50% |
| **2-of-3 majority, three neural models** | **3.50%** |
| CRNN + Tesseract **unanimity** | **0.00%** |

Three docTR-family models make **correlated** errors, so a majority vote
*ratifies the shared mistake*. Adding models does not help; adding an
architecturally **independent** model does. Tesseract earns its place precisely
because it is not a neural CTC model trained on the same data.

**Consequence:** do not build "3 fast models vote, escalate on disagreement."
Build "1 fast model + a syntax gate, escalate to an independent confirmer."

### 4. The HLA syntax gate does more than any engine choice

A ~20-line normalizer plus an HLA-shape regex measured **99.5% auto-accept at
0.00% false-accept**, routing 0.5% to review — beating every voting scheme at a
quarter of the compute. It works because residual OCR errors here are
**systematic, not random**: they are syntactically invalid HLA, and the dominant
single confusion is `*` misread as an apostrophe.

Because template geometry supplies the locus, the letters-half and digits-half of
a value are unambiguous, so `O/0`, `I/1`, `S/5`, `B/8` resolve deterministically
**by position**. This satisfies the OCR-001 invariants directly: the locus is
never inferred from token text, an unparseable value becomes `REVIEW_REQUIRED`
rather than a guess, and a first field is never expanded to a second.

### 5. Restrict the alphabet by masking CTC logits, not by swapping dictionaries

Measured: exact-match 91.0% → 97.5% for free. **Do not** attempt this by
shrinking `rec_char_dict_path`/`vocab` — the CTC output layer is sized at
training time and a shorter dictionary **misindexes silently** rather than
erroring.

Engine support differs and is not interchangeable: Tesseract takes a literal
`tessedit_char_whitelist`; EasyOCR has a first-class `allowlist` implemented as
probability masking; PaddleOCR/RapidOCR/docTR require hand-rolled logit masking.

### 6. Persian and Latin are different pipelines on the same document

HLA values are Latin+digits; patient, laboratory and date metadata are Persian.
No engine does both well. **EasyOCR `fa` on GPU is the Persian reader** (2.6×
Tesseract's character yield). The Latin path never needs a Persian model.

### 7. GPU is used only where it unlocks capability, not for throughput

The Pascal constraints are hard and vendor-confirmed:

- CUDA 13 **removed** sm_61, so `onnxruntime-gpu >= 1.27` can never run here.
  The last usable build is **1.26.x**; cuDNN must be ≤ **9.11**.
- `paddlepaddle-gpu` requires compute ≥ 7.5 — **excluded by the vendor**.
- Surya forces fp16 on GPU; GP104 runs fp16 at **1/64** rate — **excluded**.
- torch **cu126** (and cu121, verified here) ship sm_61 and bundle their own
  CUDA/cuDNN. cu128+ dropped Pascal. This is the only self-consistent GPU stack.

Verified on this machine: `torch 2.5.1+cu121`, `sm_61` present, 4.33 TFLOPS fp32,
7.5 GB free VRAM.

**Trap:** if both `onnxruntime` and `onnxruntime-gpu` are installed, ORT silently
resolves to CPU. We hit exactly this class of failure: ORT 1.29 reported
`CUDAExecutionProvider` as available, then fell back to CPU while still printing
success. **Assert the provider actually in use; never trust the available list.**

## The cascade

```
0  inventory + exact dedup            145,697 -> 33,147 unique   (4.4x)
1  DETECTION, once per unique image   185 ms      <- 86% of cost
2  cheap recognizers on shared crops   0.44 ms/crop each
     - OnnxTR crnn_mobilenet_v3_small + CTC logit mask   (Latin / HLA)
3  normalize + HLA syntax gate         free       -> ACCEPT or ABSTAIN
4  escalate ONLY abstentions
     - Tesseract psm7 + whitelist + 3x Lanczos (independent)  -> unanimity
     - EasyOCR fa (GPU) for Persian metadata on document-class images
5  still ambiguous                                -> REVIEW_REQUIRED
```

Escalation is bounded by design: stage 4 runs on the small abstention set, so its
higher per-image cost does not scale with the corpus.

## Throughput

| | |
|---|---|
| OnnxTR, single process, all cores | **4.36 img/s** |
| unique images | 33,147 |
| **full detection+recognition pass** | **~2.1 hours** |

Compared with the previous plan: RapidOCR would have been ~4.8 h and PaddleOCR
~30 h for the same pass.

## What this does NOT do

**Stage 1–2 extract text and its geometry. They do not assign an HLA locus.**
Locus assignment requires the template registry, which requires the golden
corpus, which `OCR-001` is correctly blocked on. Running this pass now is what
*unblocks* that work: it produces the text and box geometry needed to classify
documents, discover template families, and stratify-sample the 200 golden
documents from the HLA stratum rather than from raw noise.

## Consequences

- `OCR_SPEC.md` §6 stage order is superseded: PaddleOCR is no longer the primary
  reader. It stays as an optional high-recall comparator for the golden-corpus
  calibration run only, where its 6 s/image is affordable once.
- Tesseract's role changes from "second opinion on everything" to "independent
  confirmer on abstentions" **and** "the Persian fallback if EasyOCR is absent".
- A new invariant follows from §5: *a recognizer's alphabet must be restricted by
  masking, never by substituting a smaller dictionary.*
