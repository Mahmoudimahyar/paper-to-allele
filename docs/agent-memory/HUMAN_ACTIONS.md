# Human actions queue

Never put secret values in this file.

## Open

### HA-004 — Iranian histocompatibility practice must be confirmed
- **Needed by:** V1-MATCH; blocks freezing the matching spec.
- **Why:** The matching design is grounded in OPTN (US), EFI and Eurotransplant
  (EU) standards and WHO nomenclature. **No Iranian standard was consulted.**
  If Iranian practice differs on which loci are typed, how mismatches are
  counted, or how serology is reported, it outranks all of the above.
- **Decision required:** confirm with an Iranian transplant immunologist which
  loci are routinely typed, at what resolution, and how mismatch is counted
  locally. Also confirm whether the archive's lab families (Yekta, Basir,
  Gholhak, Razi) report serologic or molecular types.
- **Secret?** No.
- **Blocking now?** Blocks V1-MATCH spec freeze. Does not block MVP-HIST.

### HA-005 — Should patient names be stored in plaintext?
- **Needed by:** entity resolution (ENTITY-001); affects what identifiable data we hold.
- **Why:** The Persian pass extracted name-field cues from 8,875 reports. That
  field is the highest-PII item in the archive, is useful for linking one
  person's repeated posts, and is **irrelevant to HLA matching**. Comparing the
  two passes, Persian added only +5 laboratory markers and +360 dates — names
  were essentially its entire yield.
- **Decision required:** store the name as a **salted hash** for matching only
  (recommended — keeps the dedup value at a fraction of the exposure), or keep
  plaintext because a reviewer workflow needs to read it. `PRODUCT_CONSTITUTION`
  section 4 keeps direct identifiers hidden until mutual approval, so plaintext
  storage should be a deliberate choice.
- **Secret?** No, but the underlying data is PHI.
- **Blocking now?** Blocks ENTITY-001 design. Not blocking MVP-HIST parsing.

### HA-003 — Low-resolution threshold for mandatory human review
- **Needed by:** MEDIA-001, and every downstream OCR acceptance decision.
- **Why now:** The real archive contains **zero** thumbnail-only assets, but 77%
  of originals have a longest edge of ~520 px. The quality signal is currently
  keyed on the filename (`_thumb`) and on a missing original, so against this
  archive it never fires: low-resolution images would be classified
  `HIGH_RES_AVAILABLE` and would skip the human review the constitution requires
  before a low-resolution critical HLA value reaches Gold. Measurements in
  `docs/ingestion/ARCHIVE_CHARACTERIZATION_2026-08-31.md`.
- **Decision required:** the pixel threshold(s) separating quality bands, and
  which band forces mandatory review. A defensible starting point is: longest
  edge < 900 px => review required; 900-1280 px => review required for critical
  HLA fields; the ~0.1% above 1280 px => normal acceptance policy. **These
  numbers are a placeholder for a clinical judgement, not a recommendation the
  agent is qualified to make.**
- **Secret?** No.
- **Blocking now?** Blocks MEDIA-001 completion. Does NOT block HIST-001, which
  performs no quality classification.
- **STATUS 2026-09-02: premise corrected.** The "77% at ~520 px" figure counted
  9,581 thumbnail *copies* (`_thumb (n).jpg`) as originals (KI-009). True
  distribution of the 23,566 unique originals: 90.0% >900 px, 9.7% 561–900 px,
  0.4% ≤560 px. The decision is still needed — for the 561–900 px band and for
  the `_thumb.jpg` the export carries for every photo — but it is no longer the
  dominant accuracy risk. See `docs/ingestion/ACCURACY_REVIEW_AND_PLAN_2026-09-02.md`.

### HA-006 — py-ard / IMGT version conflict
- **Needed by:** HLA validation gate (P2 of the accuracy review), OCR-001.
- **Why now:** `HLA_VALIDATION_SPEC.md` pins IMGT/HLA 3.65, but the locked
  `py-ard` is 1.5.5 (`>=1,<2`) and `init(imgt_version="3650")` fails with
  `IndexError` (3640 too, per the research pass); `3620` loads. Verified on this
  machine 2026-09-02 (KI-011).
- **Decision required:** (a) pin IMGT 3620 with the locked library and amend the
  spec, or (b) raise the `py-ard` constraint to a 2.x release, update the OSS
  register and lockfile, and re-test 3650. The agent must not change a spec pin
  or a major dependency version silently.
- **Secret?** No.
- **Blocking now?** Blocks P2 (nomenclature validation) only; P0/P1 proceed.

### HA-001 — Local archive path (only when running real MVP-HIST ingestion)
- **Needed by:** HIST-001 real-data smoke test
- **Action:** Set `KM_TELEGRAM_EXPORT_DIR` in local `.env` to the extracted Telegram export directory.
- **Secret?** No, but machine-specific; do not commit `.env`.
- **Blocking now?** No; synthetic tests should be implemented first.
- **STATUS 2026-09-01: DONE on this machine.** Archive moved to
  `data/raw/ChatExport_2026-08-31` (gitignored) and `.env` written. Any other
  machine must repeat this; the archive is local-only and never committed.

### HA-002 — Project source-code license before public release
- **Needed by:** public/open-source release only
- **Action:** Human chooses project license. Third-party OSS licenses remain tracked independently.
- **Blocking now?** No.

### HA-008 — Label the anchored review pack (150 documents, ~2.5 hours)
- **Needed by:** every accuracy claim (KI-012); the ordering of the review
  queue; HA-003's MID-band decision.
- **Why:** the blind golden corpus (HA-007) measures the published bound; this
  pack finds where the pipeline is wrong, fast. 150 documents drawn from fifteen
  failure strata plus a clean control, with every engine's reading shown.
- **What to do:** run `uv run --frozen --extra ocr python scripts/review_pack.py`
  (already built once into `data/review/hla_pack/`), open
  `data/review/hla_pack/index.html` in a browser, enter your name, approve or
  correct each cell (Enter approves), export the labels, and hand the JSON to
  an agent. Score with `python scripts/golden_score.py --labels x.json x.json
  --hidden data/review/hla_pack/pipeline.json`. Details:
  `docs/ingestion/OPEN_ISSUES_SOLUTIONS_2026-09-02.md` issue 1.
- **Secret?** No. The pack is PHI and stays under gitignored `data/review/`.
- **Blocking now?** Blocks any accuracy number and the review-queue design.

### HA-009 — Approve the empty-cell policy (turns ~20,000 review items into one rule)
- **Needed by:** REVIEW-001 (the queue), OCR-001.
- **Why:** 24,142 REVIEW_REQUIRED cells are "label printed, cell empty" on loci
  these laboratories do not type (KI-013: DQA1 10,766, C 9,906, and so on).
  Reviewing them one by one is wasted human time.
- **Decision required:** may an anchored label with no box in its cell resolve
  to `NOT_TESTED` for a layout family where the cell is measured empty on ≥95%
  of that family's documents, with the rate recorded as provenance? This changes
  what UNKNOWN means for those cells, so it is a spec line, not an agent call.
- **Secret?** No.
- **Blocking now?** Blocks the queue's size; nothing else.

### HA-010 — Cloud model API keys, only if a synthetic-only comparison is wanted
- **Needed by:** the OCR model survey's cloud rows (Claude, GPT, Gemini).
- **Why:** no real lab-report crop may reach a cloud API (PHI). A synthetic,
  rendered sample of 220 crops exists locally for a legal comparison, and the
  adapter refuses any other input. No provider key is present, so 0 of 6 cloud
  models were called. A synthetic score says little about the real forms; the
  local engines already measured are the ones that can be deployed.
- **Decision required:** whether to fund the comparison at all. If yes, set
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` in the ignored `.env`
  and an agent runs the synthetic sample only (cap 220 requests per model).
- **Secret?** Yes: the keys. Never in Markdown or memory files.
- **Blocking now?** No.

## Closed
<!-- Move completed items here without inserting credentials. -->

### HA-007 — Label the golden corpus (the one thing blocking every accuracy claim)
- **Needed by:** OCR-001 (leaves `BLOCKED_BY_BENCHMARK` only on this), and every
  number in ADR 0008 and the extraction review, all of which are yields rather
  than accuracies until this is done (KI-012).
- **Why now:** the tooling is built and the tasks are generated. 199 documents,
  **2,189 cells**, of which the pipeline resolved 948. Zero failures over those
  948 bounds wrong-value false acceptance at **0.32%** by the rule of three; the
  document, as a unit, could only ever bound it at 1.5%.
- **What to do**, in order:
  1. **Two different people** each open `tools/golden_label.html` in a browser,
     enter their own name, and load `data/review/golden/tasks.json`. The page
     never shows the machine's answer, and each person's name seeds a different
     order, so the two readings stay independent. Roughly 4 hours each if the
     948 resolved cells are done first. Each downloads `labels_<name>.json`.
  2. Run `python scripts/golden_adjudicate.py --labels <a> <b>` to produce the
     disputes.
  3. **A third person** answers the disputes against the image and saves
     `adjudicated.json`. The two labellers must NOT settle their own
     disagreements: measured, people reconciling their own double entry make the
     entries match, sometimes by introducing new errors.
  4. Run the scorer. It exits non-zero if a single cell was resolved to
     something the corpus contradicts:
     `python scripts/golden_score.py --labels <a> <b> --adjudicated adjudicated.json`
- **Acceptance command for OCR-001 when it goes live:** that `golden_score.py`
  invocation. Its output is the evidence file `scripts/acceptance.py` records.
- **Secret?** No, but the crops are PHI: `data/review/` is gitignored and must
  stay local.
- **Blocking now?** Yes. Nothing extracted may be published to Gold until it
  passes, and no precision figure may be quoted before it.

