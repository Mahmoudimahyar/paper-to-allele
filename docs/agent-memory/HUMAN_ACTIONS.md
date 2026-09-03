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
- **What to do:** the pack is already built at `data/review/hla_pack/`.
  Double-click `serve.cmd` inside it; a browser opens on the page. Enter your
  name, then work down each document: Enter approves the row as shown, typing
  replaces it. Cells the pipeline never anchored are pre-set to NOT_PRINTED or
  BLANK, so most rows are one keystroke. Export the labels when done and hand
  the JSON to an agent. Score with `python scripts/golden_score.py --labels
  x.json x.json --hidden data/review/hla_pack/pipeline.json`.
  (Rebuild or resize with `uv run --frozen --extra ocr python
  scripts/review_pack.py --n 150 --suggestions data/review/suggestions`;
  rebuilding after the fact database changes reshuffles the strata, so finish a
  pack before regenerating it.) Details:
  `docs/ingestion/OPEN_ISSUES_SOLUTIONS_2026-09-02.md` issue 1.
- **Secret?** No. The pack is PHI and stays under gitignored `data/review/`.
- **Blocking now?** Blocks any accuracy number and the review-queue design.

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

### HA-009 — Empty-cell policy — **DECIDED 2026-09-03, implemented**
Delegated by the operator. The 95%-emptiness rule I proposed fires on nothing
(no family and locus reaches it). The right statistic is how often an anchored
cell ever RESOLVES: DPA1 0.0-0.4% and DPB1 0.0-0.5% against DQA1 3.9-11.9% and
C 11.7-28.3%. Those two loci are now `NOT_TESTED`, removing 24,663 cells from
the review queue. `config/locus_testing_rates.json`,
`kidneymatch.hla.testing_policy`.

### HA-006 — IMGT version — **DECIDED 2026-09-03, implemented**
Pin IPD-IMGT/HLA 3.62 (`3620`), the release the locked `py-ard` 1.5.5 can load;
3650 and 3640 raise `IndexError` (KI-011). A spec pinning a release the build
refuses is not a pin. Raising `py-ard` to 2.x and retesting 3650 is its own
task, with the OSS register and the lockfile.
`docs/clinical/HLA_VALIDATION_SPEC.md`.

### HA-005 — Patient names — **DECIDED 2026-09-03, implemented**
Store a **salted hash**, never plaintext. It keeps the linking value and removes
the exposure; a reviewer who needs the name has the photograph.
`kidneymatch.domain.entity_resolution.salted_hash` refuses to run without a
salt, because an unsalted hash over a short name distribution is reversible.
The salt belongs in the secret store, never in this repository.

### HA-003 — Resolution bands — **DECIDED 2026-09-03 (MID provisional)**
LOW (≤560 px, 85 documents) always requires human review. MID (561-900 px,
2,276) requires it for critical HLA fields **provisionally**, because that is
the one band where the cost is real and the evidence to set it does not exist
yet; the review pack's `mid_res` stratum measures it (HA-008).
`docs/ingestion/LOW_RES_MEDIA_POLICY.md`.

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

