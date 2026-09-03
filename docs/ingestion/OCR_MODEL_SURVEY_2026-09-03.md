# OCR engine survey: eighteen candidates against the pipeline's own recognizer

Answers the question "which of these models have we not tried, and would any of
them read these cells better?" for GLM-OCR, GLM-4.5V, PaddleOCR-VL, PaddleOCR
v5, GOT-OCR 2.0, GOT-OCR 2.5, OlmOCR-2, Qwen2.5-VL, Qwen3-VL, Claude Fable 5,
Claude Opus 4.6, Gemini 3.1 Pro, Gemini 3.5 Flash-Lite, GPT-5.2, GPT-4o,
Tesseract 5, EasyOCR and DocTR.

Twenty-two engine configurations were measured on the same 600 real crops.
Everything ran locally; **no crop of a real report was sent to any network
service** (see "Cloud models" below). Raw per-crop outputs stayed on the machine
and are not reproduced here or anywhere in the repository.

---

## 1. The benchmark, and the two ways it can mislead you

600 crops drawn with a fixed seed from `facts.sqlite`, in three strata:

* **TRUSTED** (300) — cells the pipeline resolved, the constrained decode found
  unanimous under one-pixel jitter, *and* the Tesseract confirmer agreed with.
* **HARD** (200) — cells where those signals disagree: decode `SPLIT` or
  `DIGITS_LOST`, or confirmer `CONTRADICTED`.
* **LABEL** (100) — locus-label crops. An engine that turns `HLA-A` into an
  allele is dangerous, and this stratum catches it.

Each engine returns a string per crop; the string is parsed by the project's own
`parse_allele_value` and compared with the pipeline's value. Scoring code is
identical for every engine.

**These are agreement rates, not accuracies.** Nothing here has been compared to
a human reading (KI-012). Two specific distortions have to be stated:

1. **The strata were defined using two of the engines.** TRUSTED requires
   Tesseract to have agreed, so Tesseract's 0.900 there is inflated; HARD is
   partly *defined* as Tesseract disagreeing, so its 0.515 there is deflated.
   The same applies to the pipeline's own recognizer through the decode. Only
   the engines that took no part in defining the strata — PaddleOCR, Qwen3-VL,
   the larger DocTR models — are ranked cleanly against each other.
2. **Crop framing is a variable, not a constant.** Two samples were cut: the
   padded one (0.4% of page width, 0.6% of height — the padding the Tesseract
   confirmer measured best with) and an unpadded one using the exact stored
   boxes. The pipeline's own engine on its own boxes scores 1.000 by
   construction, which is circular and is reported here only to expose the
   effect in §3.

---

## 2. Results on the 600 real crops (padded sample)

Sorted by TRUSTED exact agreement. `L→allele` counts label crops the engine
turned into an allele-shaped string; lower is safer.

| engine | TRUSTED | abstain | HARD | L→allele | ms/crop | device |
|---|---:|---:|---:|---:|---:|---|
| qwen3-vl 4B Q4_K_M (llama.cpp) | **0.997** | 0.003 | **0.910** | 0 | 982 | CPU |
| ppocrv5-en-mobile-rec | **0.970** | 0.030 | **0.910** | 0 | 13.1 | CPU |
| ppocrv5-mobile-rec | 0.963 | 0.033 | 0.855 | 0 | 26.6 | CPU |
| ppocrv5-server-rec | 0.957 | 0.043 | 0.890 | 0 | 21.1 | CPU |
| tesseract5-psm7 *(current confirmer)* | 0.900\* | 0.100 | 0.515\* | 0 | 8.3 | CPU |
| onnxtr-parseq | 0.883 | 0.117 | 0.755 | 0 | 15.8 | CPU |
| onnxtr-mobile-constrained *(the decode)* | 0.803 | 0.000 | 0.545 | **100** | 5.2 | CPU |
| onnxtr-sar_resnet31 | 0.743 | 0.257 | 0.515 | 0 | 10.9 | CPU |
| onnxtr-vitstr_base | 0.740 | 0.260 | 0.530 | 0 | 22.4 | CPU |
| onnxtr-parseq-multilingual-v1 | 0.730 | 0.263 | 0.520 | 0 | 20.1 | CPU |
| onnxtr-vitstr_small | 0.727 | 0.267 | 0.465 | 0 | 10.8 | CPU |
| onnxtr-master | 0.713 | 0.287 | 0.510 | 0 | 89.6 | CPU |
| onnxtr-crnn_mobilenet_v3_large | 0.497 | 0.503 | 0.335 | 0 | 2.0 | CPU |
| onnxtr-crnn_vgg16_bn | 0.493 | 0.503 | 0.335 | 0 | 5.6 | CPU |
| onnxtr-viptr_tiny | 0.457 | 0.543 | 0.310 | 0 | 6.6 | CPU |
| **onnxtr-crnn_mobilenet_v3_small** *(the pipeline)* | **0.440** | 0.530 | 0.265 | 0 | 2.0 | CPU |

\* inflated / deflated by the stratum definition, per §1.

## 3. The finding that matters most: the pipeline's recognizer is brittle to framing

The same engine, the same 600 cells, two crops:

| crop | TRUSTED exact | HARD exact |
|---|---:|---:|
| exact stored box | 1.000 (circular) | 0.975 |
| box + 0.4% / 0.6% padding | **0.440** | **0.265** |

A padding of a few pixels costs `crnn_mobilenet_v3_small` **56 points**, almost
all of it into abstention (0.530): the reading stops parsing as an allele at
all. PP-OCRv5 loses nothing over the same change and Qwen3-VL loses nothing.

The pipeline is therefore not merely "using a small model" — it is depending on
the detector having drawn the box exactly right. That dependency is invisible
in the yield numbers because the same detector supplies both. Any future change
to detection, preprocessing or resolution has a large, silent blast radius, and
this is the single strongest argument in this document for a second engine that
does not share the weakness.

## 4. The constrained decode turns every label into an allele

`onnxtr-mobile-constrained` scored **100 of 100** LABEL crops as parseable
alleles; every other engine scored 0. This is an independent confirmation of
ADR 0009's rule that the decode may never run before geometry, measured on real
crops rather than argued. It is working as designed, and the design is right.

## 5. Cloud models: never shown real data, and not run

A crop of a real lab report is PHI, and sending one to a third-party API is
prohibited by `AGENTS.md`. To make a legal comparison possible, a synthetic
sample of 220 rendered crops was built (HLA-shaped strings in Windows fonts, at
JPEG qualities and blur levels chosen to imitate the corpus), with the adapter
hard-refusing any input other than that sample.

**No provider credential exists on this machine** — checked by variable name
only, never by value: no `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`
or `GOOGLE_API_KEY`. **0 of the 6 cloud models were called.** Claude Fable 5,
Claude Opus 4.6, Gemini 3.1 Pro, Gemini 3.5 Flash-Lite, GPT-5.2 and GPT-4o are
therefore untested. See **HA-010**: the comparison is only worth funding if the
synthetic proxy is considered informative, and it is a weak proxy — the local
engines all score 0.99–1.00 on the synthetic TRUSTED stratum and 0.44–0.99 on
the real one, so synthetic scores do not rank engines.

## 6. Every model on the list, and its verdict

| model | verdict |
|---|---|
| **PaddleOCR v5** (mobile / server / en-mobile rec) | **Tested, full sample. Best practical result.** 4.1–21M params, Apache-2.0, CPU. |
| **Qwen3-VL** (4B Q4_K_M + F16 mmproj, llama.cpp) | **Tested, full sample.** Highest agreement of all, at 982 ms/crop on CPU — ~75× slower than PaddleOCR for +2.7 points. |
| **Tesseract 5** | Tested (already the confirmer). Blind on narrow class I cells; see KI-019. |
| **DocTR** | Tested exhaustively — all 10 recognizers OnnxTR 0.9.0 ships. `parseq` is the best of the family at 0.883. No newer DocTR release exists to chase. |
| **EasyOCR** | Tested in the earlier benchmark (`OCR_ENGINE_BENCHMARK_2026-09-01.md`); not re-run. |
| **GLM-OCR** | Feasible and installed (1,107M params, MIT, plain transformers, fp32 4.13 GiB — fits the 8 GB card). Ran the synthetic sample on CPU at 487 ms/crop (1.000 / 0.867). **The real-sample run was not done**: see §7. |
| **PaddleOCR-VL** | Feasible and installed (906M params, fp32 3.37 GiB, fits with ~2 GiB headroom). **Not run on the real sample**: §7. |
| **GOT-OCR 2.0** | Feasible and installed (560M params; fp32 weights 2.1 GiB but the SAM-style 1024×1024 tower materialises ~768 MiB attention tensors, so batch 1 only). **Not run on the real sample**: §7. |
| **GOT-OCR 2.5** | **Does not exist.** No such release from stepfun-ai; 2.0 is current. |
| **OlmOCR-2** (allenai/olmOCR-2-7B-1025) | 8.29B params — 33 GB in fp32, 16.6 GB in bf16, against a 5.5 GB budget. Native path impossible on this GPU; only viable as a Q4_K_M GGUF through llama.cpp. Installed, **not run**: §7. |
| **Qwen2.5-VL** | Research incomplete when the machine powered off mid-download; not run. Qwen3-VL supersedes it and was measured. |
| **GLM-4.5V** | ~106B parameters. Infeasible locally by two orders of magnitude, and prohibited in the cloud because it would mean sending PHI. **Not tested, and not testable here.** |
| Claude Fable 5 · Claude Opus 4.6 · Gemini 3.1 Pro · Gemini 3.5 Flash-Lite · GPT-5.2 · GPT-4o | Not tested. No credentials, and real crops may never be sent. §5. |

## 7. Why four feasible models were left unmeasured

All four were installed and smoke-tested; each was queued to run on the GPU one
after another. The machine powered off twice during that work, so the GPU phase
was **stopped and deliberately not resumed**. `docs/operations/WORKSTATION_STABILITY.md`
records what the event log says — 35 unclean shutdowns going back to 2026-06-11,
most of them long before this project existed, with no bug-check, no crash dump
and no hardware-error record — so the shutdowns are not caused by this workload,
but there is no reason to keep provoking a marginal machine for a result that
would not change the recommendation: the leader on this benchmark already runs
on the CPU in 13 ms.

The environments and adapters remain under the session scratch directory
(`%TEMP%\claude\C--Users-Mahyar-kidneymatch\<session>\scratchpad\ocrbench`),
so the runs can be completed later at low cost if the machine is fixed. They
hold about **22 GB** of model weights and eleven virtual environments; deleting
that directory costs nothing but the re-download.

## 8. Recommendation

**Adopt PP-OCRv5 English mobile rec as the second confirmer, replacing or
joining Tesseract.** It agrees with the trusted set 97.0% of the time against
Tesseract's 90.0%, and on the hard cells 91.0% against 51.5% — and unlike the
current pipeline's recognizer it is insensitive to crop padding. It reads 4.1M
parameters on the CPU in 13 ms per crop, which is ten minutes for the whole
corpus, and it is Apache-2.0.

The concrete gain is **KI-019**: Tesseract has no opinion on 18,019 resolved
cells, most of them class I, because the crops are four glyphs wide and it
returns nothing. An engine that answers on those cells converts silence into
either corroboration or a flagged disagreement, and that is what the review
queue is short of.

Two constraints on doing it:

* Adding `paddlepaddle` + `paddleocr` is a **dependency decision**, which
  `AGENTS.md` says must go with an OSS register entry and a lockfile update. It
  is a heavy dependency (a few hundred MB). Until that is decided,
  `scripts/suggest_pass.py --dump-crops` already lets the engine run from its
  own environment and hand readings back as JSON, with nothing added to the
  repository.
* **No engine here may make a finding.** A second confirmer produces
  `CONFIRMED` / `CONTRADICTED` / `UNCONFIRMED` exactly as Tesseract does; the
  value still comes from geometry, and only the golden corpus can say whether
  any of it is right.

**Do not replace the primary recognizer on this evidence.** Its 0.440 in the
table is against padded crops it never sees in production, and the strata were
partly defined by its own output. What the number justifies is a second
opinion and the golden corpus (HA-007, HA-008) — not a swap.
