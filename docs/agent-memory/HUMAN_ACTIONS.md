# Human actions queue

Never put secret values in this file.

## Open

### HA-013 — Google Vision: the key is not on this machine, and the policy still forbids it
- **Needed by:** the requested head-to-head against the reviewer's 220 labels.
- **Why:** two things are in the way, and only a person can clear either.
  1. **The key is absent.** `.env` holds nine variables and none of them names
     Google, Vision, GCP or a service account, and no other `.env` file exists
     in the repository. Nothing was sent anywhere; the benchmark simply cannot
     run.
  2. **The versioned decision forbids it.** `docs/ingestion/CV_RESEARCH_2026-09-05.md`
     s6 "Do not do" ends with "any cloud OCR/VLM or sending an image off the
     machine". That is a policy, and policy is the human's to change, so the
     instruction to test Google Vision conflicts with a source-of-truth
     document rather than overriding it silently.
- **Decision required, in two parts:**
  - name the variable and set it in the local `.env` (never in a document, a
    commit, or this file);
  - amend `CV_RESEARCH_2026-09-05.md` s6 to say what may leave the machine.
    The narrow amendment the pipeline actually needs is **value crops only** —
    a padded rectangle around one allele, carrying no name, no laboratory, no
    date and no identifier. The broad one is **whole pages**, which is where
    the evidence would be most useful (the largest refusal bucket in the whole
    pipeline is 23,719 cells whose label was found and whose value box was
    never detected) and which does send the patient's name and the laboratory's
    letterhead to Google.
- **Secret?** The key is. It goes in `.env` only.
- **Blocking now?** Blocks the Google Vision comparison and nothing else. Every
  other measurement in this round was made with the local engines.

### HA-014 — Seven cells the pipeline reads and the reviewer marked NOT PRINTED
- **Needed by:** the accuracy figure on the 220-label set; these are 7 of the
  9 remaining contradictions.
- **Why:** the review page showed **no crop for 50 of the 220 labelled cells**,
  because the pipeline had found neither a label nor a value box there. The
  reviewer therefore had to hunt the whole page for a locus whose printed label
  our recognizer had misread, and answered NOT PRINTED on 31 of them. On the
  seven the pipeline now resolves, the page evidence says the value is printed:
  * one DQB1 cell whose row label reads `HLA-DOBI` and whose two value columns
    hold two DQB1-prefixed alleles;
  * three DRB3/4/5 cells on a 20-box low-resolution page whose grouped row
    holds two gene names in the value columns;
  * three DRB3/4/5 cells on a high-resolution page whose grouped row prints one
    gene name in the first value column, the second column being blank.
- **What to do:** the pack has been rebuilt, and those cells now show a crop.
  Re-answer the seven. If the reading stands, the pipeline is right and the
  earlier answers should be corrected; if it does not, these are false
  acceptances and outrank everything else in the queue.
- **Secret?** No.
- **Blocking now?** Blocks calling the 220-label figure settled.


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
- **STATUS 2026-09-05: 165 of 1,650 cells labelled (15 documents).** Scored
  with `uv run --frozen python scripts/pack_score.py --export <file>`. The
  DRB3/4/5 rows of those 15 documents were labelled under the old three-cell
  question and are NOT ground truth (KI-021): reload the page (Ctrl+F5), and
  the row shows "re-confirm" — tick the genes printed, nothing else. The server
  runs on http://localhost:8766 (port 8765 is taken by another program).
- **STATUS 2026-09-05 (later): 187 cells labelled (17 documents), scored, every
  miss traced (ADR 0009 §7).** The page now shows the Telegram messages posted
  with each image — a collapsible "Messages" block under the tags, with the
  caption's role claim beside Role — after Ctrl+F5. The pack's own crops and
  suggestions are from before this session's fixes and are deliberately NOT
  rebuilt (the labels are keyed to them); the next pack will carry the fixes
  and a `tilted` stratum. Two things the labels can settle next: DRB3/4/5 rows
  where the page marks a gene "repaired" (was the printed name really DRB5?),
  and cells marked "promoted" (760 corpus-wide). One caveat on the labels so
  far: the page pre-sets NOT_PRINTED on a row the pipeline never anchored, and
  Enter accepts it — on 8 of 21 such rows the pipeline now reads a value
  (3 of them DRB3/4/5 rows with gene names PP-OCRv5 confirms), so a
  NOT_PRINTED accepted by Enter is a default, not a reading of the page.
- **STATUS 2026-09-05 (evening): each answer now takes an optional note.**
  Press `N` on a row (or click `note`), write one line, Enter or Esc saves it;
  each page has a note of its own under the tags. The note survives changing
  your answer, rides back in the export beside the labels, and is what says
  WHY a cell is wrong rather than only that it is — which crop is cut, which
  reading looked right, what made the row hard. `pack_score.py` reports how
  many notes fell on each outcome; the text itself is read from the export by
  whoever is debugging, and is never copied into a report or committed.

### HA-012 — May a measured empty cell be NOT_TESTED, per page?
- **Needed by:** ~15,000 review items (the largest single class left in the
  queue); nothing else is blocked.
- **Why:** `scripts/cell_ink_pass.py` measures the ruled cell of every printed
  locus label the row rules found empty, on the page itself: 14,719 measured as
  paper, 3,831 hold ink no engine boxed, 793 could not be measured. HA-009
  already retires a (family, locus) pair a laboratory measurably never fills —
  a per-LABORATORY verdict from a committed statistic. This would extend the
  same status to a per-PAGE measurement, which is a different claim: "this
  page's row is empty", not "this laboratory does not run this test".
- **What to do:** decide whether a cell whose ruled row measures as paper may
  be `NOT_TESTED`. Two things to weigh, both measurable: on the reviewer's
  labels the measure has never yet called a cell paper where a value was read
  (19 cells the reviewer marked BLANK, 4 NOT_PRINTED, 0 with a value), and the
  adversarial review of 2026-09-05 lists the ways a row-wide region can read
  as paper when it is not (a value stacked under its label, a shadow removed
  as a ruling, a band spanning two printed rows). A middle answer is available:
  order the review queue by the measurement — paper first, cheap to confirm —
  without changing any status.
- **Secret?** No.
- **Blocking now?** No. The measurement is recorded in `cell_ink` either way.

### HA-011 — Codify the DRB3/4/5 row's grammar in the spec, and decide two semantics
- **Needed by:** the row grammar v2 (`GROUPED_DRBX/v2`: bare numbers on the
  row → review with candidate genes; a prefixed allele → presence plus a
  proposal), and any use of DRB3/4/5 beyond presence in matching.
- **Why:** the licence to read a gene NAME from token text inside the grouped
  row — geometry fixes the row, the printed header enumerates the admissible
  set — lives in ADR 0008 Decision 4. The spec outranks an ADR, and
  `OCR_SPEC.md` §2 forbids assigning a locus from token text without naming
  this exception. Measured corpus-wide (`CV_RESEARCH_2026-09-05.md` §4): the
  row prints gene names 97% of the time, bare numbers on 48 documents,
  prefixed alleles on 16.
- **Decisions required:** (a) accept codifying the enumeration licence in
  `OCR_SPEC.md` §2 and `HLA_VALIDATION_SPEC.md` §7 (per-gene presence,
  expression, optional allele proposal; storage per gene; review unit the
  printed row); (b) whether a `N`/null suffix on a DRB3/4/5 allele
  (NOT_EXPRESSED) may ever feed matching, or stays REVIEW_REQUIRED for
  matching purposes until an immunologist rules (HA-004); (c) whether a
  DRB1-derived candidate set may be SHOWN to a reviewer as a hint on a bare
  number (never bound by the pipeline).
- **Secret?** No.
- **Blocking now?** Blocks grammar v2 only; the one-row review question and
  presence typing need no spec change.

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

