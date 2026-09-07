# Human actions queue

Never put secret values in this file.

## Open

### HA-024 — Caption blood groups on a two-person page
- **Needed by:** any use of 153 ABO and 136 Rh values.
- **Why:** D4-b (2026-09-07) sent the 66 PRINTED blood groups on comparison
  sheets to review, because `fact` has no subject and a group on a page that
  carries two people cannot be recorded for either. 153 ABO and 136 Rh values
  on comparison sheets come from the CHAT instead (`source='CAPTION_CLAIM'`)
  and stand RESOLVED. The chat says what the poster's group is; on a page that
  pictures two people it does not say which of them the poster is. It is the
  same attribution problem, and the operator scoped D4-b to the printed 66.
- **Decision required:** (a) send these to review too, one statement
  (`UPDATE fact … WHERE source='CAPTION_CLAIM' AND field IN ('ABO','RH')` joined
  to `comparison_sheet=1`), losing 153/136 resolved values; or (b) keep them,
  on the reasoning that a poster who writes "my group is O+" beside a two-person
  sheet is the recipient's side far more often than not — a claim nobody has
  measured. Recommendation: (a) until round five measures the sheet population.
- **Secret?** No. **Blocking now?** No; blocking the tiered export's tier for
  these 289 values.

### HA-021 — `verify_repo.py` and CI install an extra that can no longer run the suite
- **Status:** DECIDED 2026-09-07 (D13-a) — the gate, CI and bootstrap install
  `hist hla image ocr`, the smallest set matching what `src/` imports;
  `test_harness_baseline` pins all four in all three places.
- **Needed by:** every claim of the form "the gate is green". It is not, and it
  has not been for longer than this branch.
- **Why:** `scripts/verify_repo.py` pins `EXTRA = "hist"` and CI runs
  `uv sync --frozen --extra hist` before it, but the code that gate checks now
  imports packages that live in OTHER extras:
  `src/kidneymatch/hla/drbx_consistency.py:46` imports `pyard` (extra `hla`)
  at module scope, and `src/kidneymatch/ocr/{crops,ctc,ink,rulings}.py` import
  `cv2`/`numpy` (extras `image`, `ocr`). Measured in this worktree:
  - `uv run --frozen --extra hist mypy src` — 36 errors in those four OCR
    files, all cascading from "Cannot find implementation or library stub for
    module named cv2". Adding `--extra image --extra ocr` to the same command:
    **Success, no issues found in 48 source files**.
  - `uv run --frozen --extra hist pytest -q --cov` — 7 collection ERRORs, every
    one `ModuleNotFoundError: No module named 'pyard'`. Reproduced on a single
    file that no branch has touched:
    `uv run --frozen --extra hist pytest tests/unit/test_drbx_consistency.py`.
  - All eight files involved are byte-identical to `main`, so this is not a
    branch's doing. With the project interpreter the suite is green:
    `.venv/Scripts/python.exe -m pytest tests -q` exits 0 over 1,631 tests, and
    `-m mypy src` reports no issues.
- **Decision required:** which extras the gate and CI install.
  `--extra hist --extra hla --extra image --extra ocr` is the smallest set that
  matches what `src/` imports; a single `all` extra is the other shape. It is a
  human decision because it raises CI install cost and because
  `tests/contracts/test_harness_baseline.py:91-93` pins the string
  `--extra hist` in THREE places at once (CI workflow, bootstrap,
  `verify_repo.py`) — the contract has to move with them, and an agent must not
  quietly relax a harness contract to make its own gate green.
- **Secret?** No. **Blocking now?** Yes for any statement that
  `python scripts/verify_repo.py` passed. Not blocking the extraction work,
  which runs and is verified under the project interpreter.


### HA-020 — The column direction may not be promoted on the default pack
- **Needed by:** any decision to keep `ADR0008/below-rule` — the reading that
  takes a value from the cell BENEATH its own label instead of along a row. It
  writes 364 cells on 290 pages and NOT ONE of them has ever been read by a
  person.
- **Why:** the direction's own safety case names a sample of **>= 100 column-read
  cells**, because the shape it can get wrong — a header row over two subject
  rows — is invisible to every gate it has unless the printed table draws a
  line between the two values. The ruling gate catches the ruled case and costs
  1 cell of 365; `review_pack.py`'s `below_rule_unruled` stratum is the 195 of
  198 two-box cells where no line is drawn, and `below_rule_role_unknown` the
  pages whose ROLE nobody could read.
- **Decision required:** cut and label a pack at `--n 600` before any promotion.
  Measured on the merged build with the repass applied to a copy of the live
  store: `--n 600` draws 64 documents carrying **116** column-read cells;
  `--n 300` draws 35 and 66; the default `--n 150` draws 21 and 41. The default
  pack is a sighting shot. A single contradiction in the unruled stratum
  refutes the direction for that stratum and the group is withdrawable whole
  (`source='below-rule'`, `rule_id='ADR0008/below-rule'`).
- **What has been read so far:** nothing. Of the 122 labelled documents, 20
  carry no layout family, and the four findings reach 4 of those — 3 under the
  tie clause (24 labelled HLA cells, 12 correct / 11 abstained / 1
  contradicted, unchanged by the pass) and 1 under the prefix repair (8 cells,
  2 missed -> correct, 0 worse). The left-out fit and the column direction hold
  **zero** labelled pages between them.
- **Secret?** No. **Blocking now?** Not extraction. Yes for treating a
  column-read HLA value as something a match may rest on.


### HA-017 — `AGENTS.md`'s locus rule now has a documented exception
- **Status:** DECIDED 2026-09-07 (D12-a) — `AGENTS.md` and `.claude/rules/ocr.md`
  now name the three prefix routes as the exceptions, each withdrawable by its
  `source` (`prefix-bound`, `anchor-row-prefix`, `column-bound`).
- **Needed by:** nothing is blocked; this is a wording debt an agent must not
  pay itself.
- **Why:** `AGENTS.md` says "Geometry/template cell defines HLA locus; OCR text
  alone may not assign locus", and `.claude/rules/ocr.md` repeats it. The
  operator decided in a round-two note that a fully-qualified allele may name
  its own locus where the page labels nothing, and that is recorded with its
  gates and its measurements in `CV_RESEARCH_2026-09-05.md` s12
  (`scripts/prefix_bind.py`, 4,767 cells, no new contradiction on 561 labels).
- **Decision required:** reword the sentence in `AGENTS.md` so the constitution
  and the code agree — or reverse the decision, in which case every fact with
  `source='prefix-bound'` is withdrawn as a group, which is why they carry it.
- **There is now a SECOND documented exception, and the wording must cover it.**
  `scripts/column_bind.py` (`CV_RESEARCH_2026-09-05.md` s12-b) takes the locus
  from the printed prefix on a comparison sheet with one filled column, and
  takes the PERSON from which column the values sit in. So the sentence has to
  admit two things, not one: a fully-qualified allele naming its own gene, and
  a printed column heading naming the subject. Both groups are withdrawable on
  their own — `source='prefix-bound'`, `source='column-bound'` — and the
  column-bound facts additionally record in `rule_id` which ROLE source gated
  them (measured over the 276 binds the shipped code makes: `CAPTION_CLAIM` 150
  = 54%, `FORM_FIELD_BARE` 84 = 30%, a strong printed field 42 = 15%), so the
  operator may withdraw the weakest tier alone rather than all of it.
- **Two further points for the same wording pass, both measured:** 5 of the 276
  bound pages label one or three OTHER loci, which s12's phrase "a page that
  labels no row" does not cover — the fence is per-locus in both passes, and
  either the wording says so or a page-level anchor fence is wanted instead;
  and `find_anchors` does not see a bare `DRB1*` box as a label (the star stops
  `canonical_locus_label`), which `column_bind.py` handles by tainting the
  locus rather than by treating the stub as an anchor.
- **Secret?** No. **Blocking now?** No.


### HA-022 — A page that pictures two people has no way to be recorded
- **Renumbered** 2026-09-07 from HA-019, which two parallel merges had also given
  to the blood-group window entry below; code cites this one as HA-022.
- **Needed by:** nothing today; 15 comparison sheets that PRINT two subjects
  are refused to review because of it (a further 25 are refused because a
  column that should be blank is not, which is a different question and carries
  a different reason), and every future two-subject form will be.
- **Why:** `fact` is keyed `(sha256, field, extraction_version)` with no
  subject column, and ENTITY-001's "a conflicting blood group or role blocks a
  link rather than weakening it" is written for one subject per document. So
  `scripts/column_bind.py` binds only where ONE column is filled and refuses
  the rest to `REVIEW_REQUIRED` with crops (`source='column-bind-refused'`).
  That is the conservative branch, not a design. `docs/architecture/
  DATA_MODEL.md`'s `FieldClaim.subject_candidate_id` already anticipates
  subject-keyed claims, so the target model has room for the answer.
- **Decision required:** whether a document may carry two subjects' facts at
  all, and if so what `fact`'s key becomes, what matching does with the second
  set, and how entity resolution links each one. An agent must not invent this.
- **Secret?** No. **Blocking now?** No.


### HA-023 — Keep the printed Bw4/Bw6 epitopes as a consistency gate?
- **Renumbered** 2026-09-07 from HA-018, which two parallel merges had also given
  to the two-person blood-group entry below; `glyphs.py` cites this one as HA-023.
- **Needed by:** nothing; this is evidence currently being thrown away.
- **Why:** `src/kidneymatch/ocr/glyphs.py` now reads `B*35,*51,Bw4,Bw6` and
  DROPS the tail, because the epitopes are serology and not alleles. But they
  are patient-specific, not a template constant: expected-versus-printed on the
  corpus is 38/80/113 on the diagonal against 5 off it, and every one of the 5
  is "the alleles imply Bw4+Bw6, the page printed Bw4 only" — a truncated tail,
  not a misread. Used as a gate, the epitopes would catch **50% of single
  misread digits** (2,067 of 4,114 admissible substitutions change the epitope
  set), which is the one error class no other gate on this path can see.
- **Decision required:** whether a printed Bw set contradicting the parsed
  alleles' serology should send the cell to `REVIEW_REQUIRED`. Cost measured:
  5 of 236 decidable tokens. It needs a versioned Bw4/Bw6 table from
  IPD-IMGT/HLA — never one an LLM supplies — and B*15/B*27 are undecidable at
  the first field, so they must abstain.
- **Secret?** No. **Blocking now?** No.


### HA-016 — Label the second round (60 documents, none seen before)
- **Needed by:** every value written by a pass added after the first round.
  None of them has ever been checked by a person.
- **Where:** `data/review/hla_pack_r2/`, served on **port 8767** — its own port
  on purpose, because the page keeps answers in the browser's storage for one
  origin and round one must stay intact on 8765.
- **What is in it:** 60 documents, 660 cells, none of the 20 already answered.
  Built with `--skip-labelled` against the first export and weighted so that
  **22 of the 60 carry an assertion nobody has checked**: `template_band` (2),
  `second_reading` (2), `whole_page` (2), `two_engine_reread` (5),
  `drbx_reread` (4) and `sloped_row` (7). 539 of the 660 cells show a crop.
  The remaining 38 are the first round's uncertainties, and 3 are a clean
  control.
- **What is most useful:** a wrong value is worth more than a right one. These
  strata exist because each is a way the pipeline could be confidently wrong,
  and a single contradicted cell in one of them is worth more than fifty
  confirmations. The note field is read — the seven notes from round one were
  the best diagnostic this project has had.
- **Secret?** No. **Blocking now?** Blocks calling any of the new passes safe.


### HA-015 — `A*24,02`: two alleles, or one allele at two fields?
- **Status:** DECIDED 2026-09-07 — a comma between two numbers separates two
  alleles (`A*24,02` = A*24, A*02). Only the comma carries it; the period,
  semicolon and slash forms still need the second star. `parse_allele_values`
  and `tests/unit/test_printed_pair.py` hold the rule.
- **Needed by:** 1,025 value tokens on 491 documents that currently go unread.
- **Why:** some forms print both alleles of a locus in ONE box. Where the
  second half carries its own star (`A*24,*02`) that is unambiguous and the
  pipeline now reads both (1,819 tokens on 890 documents). Where it does not
  (`A*24,02`) there are two readings and no way to choose from the glyphs:
  two alleles with the star not repeated, or the two-field allele `A*24:02`
  written with a comma where nomenclature uses a colon. Guessing either way
  breaks a rule the project states outright — invent a second allele, or
  promote a first-field reading to a second field (`OCR-001`).
- **Decision required:** for each laboratory that prints this, does a comma
  between two numbers separate two alleles or two fields of one? A page of
  each form beside its report would settle it; so would one lab's answer.
- **Secret?** No.
- **Blocking now?** Blocks 1,025 tokens. Nothing else.


### HA-013 — Google Vision: DECIDED 2026-09-05, whole pages permitted
- **Decision:** the operator set `GOOGLE_VISION_API` in the ignored `.env` and
  chose the **broad** option: whole report pages may be sent to Google Cloud
  Vision, not only value crops. They were told a whole page carries the
  patient's name and the laboratory's letterhead, and chose it because the
  evidence is only useful there — the largest refusal bucket in the pipeline is
  23,719 cells whose label was found and whose value box was never detected,
  and a crop cannot say whether a better detector would have boxed it.
- **Recorded in:** `docs/ingestion/CV_RESEARCH_2026-09-05.md` s7, which
  replaces the s6 prohibition and states what is still not permitted: no other
  cloud service, no cloud call from a pass that writes a fact, no key outside
  `.env`, and no walk of the corpus without an explicit document list.
- **Secret?** The key is, and it stays in `.env`.
- **Blocking now?** No longer blocking.

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
- **Status (a): DECIDED 2026-09-07 (D10-a)** — the enumeration licence is codified in
  `OCR_SPEC.md` §2 (exception 1) and `HLA_VALIDATION_SPEC.md` §7. (b) unchanged: a
  null-suffixed allele stays REVIEW_REQUIRED for matching until HA-004. (c) not
  taken up. (d) unchanged: the 621 token-anchored cells stand and round five measures them.
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
- **Decision (d), added 2026-09-07:** whether the enumeration licence survives
  when the header is PRINTED BUT UNREAD. `TOKEN_ANCHORED_DRBX/v1`
  (`ocr/drbx.resolve_token_anchored_drbx`, `scripts/drbx_token_repass.py`)
  places the row from the page's own label pitch on pages carrying no readable
  header, and reads the gene from the token standing on it. ADR 0008 Decision 4
  grants the licence "only because the header prints the admissible set", so
  this extends it.
  - **Yield, re-measured 2026-09-07 read-only against the live stores:** 479
    pages, 621 PRESENT cells (DRB3 349, DRB4 230, DRB5 42). An earlier version
    of this entry said "578 of 579 accepted rows ... header-shaped on 534";
    that pair of numbers came from a permissive reading of gates G3/G4/G9 and
    from route (c) being absent, and no shipped build produced it.
  - **What was measured in its favour:** on 476 of the 479 accepted rows a box
    DOES stand in the label column of the placed row — 394 carrying the
    header's `DR` stem in a spelling no header pattern reads, and 6 more
    spelling an enumeration the damage-tolerant pattern reads but standing
    where the geometry gate will not call it a header. The enumeration is
    printed and merely unread.
  - **What was cut to match the thinner licence:** PRESENT only (no absence is
    ever certified on this route), no S-for-5 repair, the strict `DR[B8]` stem,
    and twelve geometry gates.
  - **The residual risk a reviewer of (d) must weigh, which geometry cannot
    gate** (route (c)/stage-1 required fix 7): the proposal's own risk (1) is a
    form that prints THREE separate headings across the value columns with one
    of them unread. On such a page the "row" the pitch places is a row of that
    table rather than the grouped row, and no geometric test distinguishes the
    two — the gates measure where a box stands, not what table it belongs to.
    That residual is bounded ONLY by DRB1 concordance, and the bound is a
    rule-of-three one, not a measurement of the failure: on the 479 accepted
    pages, 438 read a two-field DRB1 corroborating 573 of the 621 genes, with
    479 CONSISTENT, 0 FORBIDDEN_GENE_PRESENT and 0 EXPECTED_GENE_ABSENT. Zero
    failures in 573 gives an upper bound of 3/573 = **0.52%** on the
    corroborated share, and says nothing at all about the 48 genes no two-field
    DRB1 could check. No labelled page carries one of these calls.
  - **How to withdraw it:** every fact carries `rule_id='TOKEN_ANCHORED_DRBX/v1'`
    and `source='token-anchored-drbx'`, both now emitted by the RULE and not
    only by the one-off pass, so a full re-extraction reproduces them. The
    `token_anchored_drbx` review stratum is keyed on the rule_id for the same
    reason.
- **Decision (d2), added 2026-09-07 — the same question about route (c),** the
  widened grouped header (`GROUPED_DRBX_WIDENED/v1`,
  `ocr/drbx.GROUPED_DRBX_HEADER` + `find_grouped_headers`). Here the header IS
  read, but only by a damage-tolerant pattern, and the page's own row pitch is
  what says the box is a header at all.
  - **Yield, measured 2026-09-07:** 104 of the 9,207 no-header pages, 312 gene
    cells — 119 PRESENT, 60 ABSENT, 91 REVIEW_REQUIRED, 42 UNKNOWN. By branch
    (pages, a page can need two): b-slot-glyph 39, slash-as-4 29, final-3 16,
    b-slot-empty 16, bla 4.
  - **Why it needs a human and not just a test:** unlike the token route this
    one writes ABSENT — a clinical negative — and no labelled page carries one
    of its calls, so its precision is entirely unmeasured. The nearest labelled
    stratum, a DRB3/4/5 call from an add-on source on a page whose header only
    the damage-tolerant pattern reads, is wrong 5 times in 20.
  - **The gate before promotion:** cut a pack of at least 40 of these rows —
    `python scripts/review_pack.py --only widened_drbx_header --n 40`, which
    spreads the sample across the four widenings rather than filling with the
    commonest — and require 0 false acceptances. Until then these are calls the
    pipeline makes and nobody has checked.
  - **What was already cut without waiting for the answer:** the `final-3`
    branch no longer certifies absence. A header read by substituting a `3` for
    its printed final `5` has none of the three measurements that license
    S-for-5 inside a cell (corpus-wide the final slot reads `5` 13,555 times,
    `S` 975 and `3` 25), so on those 16 pages the two-token ABSENT is
    REVIEW_REQUIRED instead: 15 cells moved, the 24 PRESENT kept.
  - **How to withdraw it:** `rule_id='GROUPED_DRBX_WIDENED/v1'` on every cell,
    and `source='widened-drbx-header:<branch>'` naming the widening. The
    distinct rule_id also keeps `drbx_ink_pass.py` and `drbx_reread.py` off
    these pages, which costs nothing — `scripts/precision_gates.py` gate 2
    withdraws every add-on DRB3/4/5 call on a page with no cleanly spelled
    header, and 0 of the 104 carries one.
  - **What route (c) is actually worth,** so the answer is not given on an
    inflated number: 46 of the 104 pages the token route would have placed
    anyway (62 PRESENT cells; turning the widening off moves that route from
    479/621 to 525/683). Of the 58 it could not have read, the token route
    refuses 39 on its own gates and could never have reached 19.
- **Secret?** No.
- **Blocking now?** Blocks grammar v2 only; the one-row review question and
  presence typing need no spec change. Decisions (d) and (d2) do not block
  either route from being reviewed — that is what the strata are for — but they
  do block treating their calls as settled.

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

## HA-018 — a blood group on a page carrying two people
- **Acted 2026-09-07 (D4-b):** the 66 PRINTED groups are in review (`sheet_abo_review.py`, `source` `LABORATORY_PRINTED|sheet-review/v1`, `--undo`). Caption-claimed groups on the same kind of page are HA-024.

- **Status:** OPEN. Not blocking extraction; blocking any use of these 66 groups
  in matching.
- **What was found:** `extract_facts` downgrades a comparison sheet — a page
  printing two subjects — for the HLA loci only. ABO and Rh are not downgraded,
  so **64 comparison sheets already ship a RESOLVED blood group**, and the
  doubled-cell collapse (`scripts/abo_repass.py`) adds 2 more. The document gets
  one blood group; the page describes two people.
- **Why an agent must not decide it:** refusing the 2 while leaving the 64 would
  be an inconsistency dressed as a safeguard, and withdrawing all 66 discards
  readings that may well be correct for the subject the report is about. Which
  subject a comparison sheet's blood-group field belongs to is a question about
  these laboratories' forms, not about this code.
- **What to do:** open a handful of the 66 and say which of these holds:
  1. the blood-group field on a comparison sheet always describes the patient
     (then keep all 66, and record why);
  2. it may describe either subject (then all 66 become REVIEW_REQUIRED, and
     the comparison-sheet downgrade extends to ABO and Rh);
  3. it depends on the form family (then the rule is per-family, and the
     families need naming).
- **Find them:** `SELECT f.sha256 FROM fact f JOIN document d USING (sha256)
  WHERE f.field='ABO' AND f.status='RESOLVED' AND d.comparison_sheet=1 AND
  f.extraction_version='facts/v1'`
- **Secret?** No. The pages are PHI and stay in the local, gitignored store.
- **Blocking now?** Not extraction. Yes for MATCH-ABO-001: a blood group that
  may belong to the other person on the page must not gate a match.

## HA-019 — the blood-group cell window: three decisions only a person can make

- **Status:** OPEN. Not blocking extraction; blocking promotion of the
  centre-band readings, blocking a settled answer on strict-never-worse, and
  blocking the placebo gate the acceptance for this rule was written around,
  which the shipped rule does not meet at one shift and cannot.
- **What shipped:** `documents/abo.py` admits a value that misses its label's
  LINE when the page's own rulings put it in the label's ROW
  (`AboRescue.BAND`), and, on a page that rules nothing, when it sits within
  0.75 label heights ABOVE the label's centre behind six gates
  (`AboRescue.CENTRE`). Both routes refuse a token contradicted by a partial
  printed in the label's own cell.
- **The numbers, and which layer each belongs to.** These were confused in the
  first version of this entry and the confusion is the reason it was rejected:
  a `read_abo` count is not a published value.
  - *reading level*, `scripts/abo_window_check.py` over 23,485 documents, raw
    frame: **93 gain a reading (42 band, 51 centre), 0 values change, 1 is
    LOST**, and 12 review reasons become specific. Levelled frame: 88 (44
    band, 44 centre) — the pair is the frame discriminator.
  - *facts level*, dry run of `scripts/abo_label_repass.py` against the live
    stores: **31 newly published centre, 13 newly published band, 12 rows the
    caption alone had answered re-attributed to the form, and 13 band
    candidates written as REVIEW items carrying a crop**.
  - `scripts/abo_repass.py` writes 34 more rows from a rescued reading (17
    band, 17 centre); 4 documents are resolved by the grid that are not
    resolved without it.
  - On the store with both passes applied the group is **42 band ABO rows (29
    RESOLVED, 13 REVIEW_REQUIRED) and 38 centre ABO rows**, plus 57 RH rows.
  - 1,287 HLA cell labels: **unchanged** (616 correct / 513 abstained / 121
    missed / 19 partial / 18 contradicted before and after). No ABO or RH cell
    is labelled, so this rule cannot move that score in either direction.
- **Decision 1 — strict-never-worse.** The one lost document is a cell the
  pipeline resolves today on ONE engine's Rh sign, while the other engine's
  box, a third of a line away, reads the opposite sign. The rescue makes the
  cell doubled and sends it to a person. The mainline binder keeps the strict
  reading in the equivalent case. Which is right is a policy question: is a
  cross-engine sign disagreement over one field a reason to withdraw a shipped
  value, or is the strict reading privileged because the window was designed
  around it? The code currently withdraws it.
- **Decision 2 — the centre band has no human check.** NO labelled document is
  among the centre-band gains. 35 of 35 with a caption agree on the letter and
  33 of 33 on the sign, but a caption is the poster's claim, not an independent
  reading.
- **Decision 3 — the placebo gate this rule fails, and why it cannot pass it.**
  The acceptance asks that a translated anchor or a size-matched decoy "must
  not exceed the shipped counts by more than +2 admissions".
  `scripts/abo_window_check.py --placebo translated|decoy|direction` now gates
  on exactly that — every extra admission, not only ones whose value differs —
  prints the leak and the published leak beside it, and exits non-zero when a
  gate fails. Measured over the live stores:

  | placebo | reach | leak | leak that would be PUBLISHED |
  |---|---|---|---|
  | -1.0h | +202 | +1 | 0 |
  | +1.0h | +10 | +4 | 0 |
  | -1.5h / +1.5h | +1 / +1 | +1 / +1 | 0 / **1** |
  | -2.0h / +2.0h | 0 / 0 | 0 / 0 | 0 |
  | -3.0h / +3.0h | +1 / 0 | +1 / 0 | 0 |
  | decoy (140,380 candidates) | +33 | +2 | **1** |
  | wrong direction | 0 | 0 | 0 |

  Three of these fail the gate as worded and the tool says so. The ±1.0h
  failures are structural: `_MAX_BAND_HEIGHTS` is 2.0, so a label moved one of
  its own heights is still inside its own printed row, and a rule whose cell IS
  the row is required to find the same cell there. The collapse to +1 at 1.5h
  and to 0 at 2.0h is the signature of a rule that follows a printed row rather
  than one that merely reaches. The decoy reach fails for a different reason:
  +2 absolute admissions is not a meaningful bar over 140,380 candidates, and
  the statistic that answers the question is the RATE — **0.024% of decoys
  admit a rescued value against 0.764% of printed field labels, 32.5x**.
  - Two entries in that table are the residual risk and they are real: at a
    +1.5h label displacement, and at one decoy in 140,380, the band route
    admits a value that DIFFERS from the true read and two engines agree on it,
    so `reconcile_abo` publishes it. Nothing in the rule can tell a mis-placed
    label from a correctly placed one; that is what a placebo measures.
  - **What is asked of a person:** approve the ±1.0h deviation as a measured
    property of a row-based cell rule, or require a tighter `_MAX_BAND_HEIGHTS`
    (which costs band gains and has not been measured at any other value), and
    say whether the two published leaks above are acceptable at those rates.
  - Not reproduced and not claimed: the pinned "~0.04%/decoy vs ~0.56%/anchor
    (12.7x)". The decoy population it was measured over (45,670) was never
    defined in reproducible terms; the definition used here — every Persian box
    within 20% of the label's height whose text is not itself a blood-group
    value, promoted one at a time — gives 140,380, and its own numbers are
    printed above. Re-reading the band at the TOKEN's x rather than the
    anchor's (the reviewer's residual) was measured and NOT shipped: it costs 5
    of the 42 band gains and changes no leak (+1.0h leak stays 4, -1.0h rises
    to 2).
- **What to do about the centre route:** read at least 20 of its documents.
  They carry the stratum `abo_centre_rescue`, which is FIRST in
  `scripts/review_pack.py::STRATA` and weighted 100 of 559 for exactly this
  reason: `choose` takes one document per stratum and then
  `round(room * weight / total) - 1` more, plus `MIN_DRAW`'s floor of 20 before
  the weights are applied at all. Measured on the merged build (the four
  no-family strata and their two floors present, the repass applied to a copy):
  the default `--n 150` draws **23**, so the 20 this decision waits on are in
  every default pack. The band route is weighted 12 and
  draws 3 a pack, so its 13 uncorroborated candidates need about five packs, or
  a raised weight, if they are wanted sooner. Promote a route only at >= 95%
  agreement; withdraw it otherwise. Both weights should come down once a round
  has answered them.
- **Also worth a person's eye:** the per-family offsets are tight (FORM#1
  -0.72..-0.63h over 42 documents), which reads as a fixed template relation
  rather than drift. The principled replacement for a generic band on unruled
  pages is an ADR 0007 per-family ABO relation.
- **Find them:** `SELECT sha256, rule_id, status FROM fact WHERE field='ABO'
  AND rule_id LIKE 'abo/anchored-cell+%' AND extraction_version='facts/v1'`.
  Every pass that publishes one of these writes that string —
  `extract_facts.py`, `abo_label_repass.py` and `abo_repass.py` all call
  `documents.abo.rule_id_for`, and the RH row beside it carries the same
  marker. A page is marked only when the box the value was READ FROM was
  rescue-admitted, so the group holds no page the rule did not change.
- **One more false sentence removed on the way past.** A row the caption pass
  answered and a repass later re-read from the form kept
  `engine_version='caption-abo/v1'` — the reader of a chat message, named
  beside a value that came off a photograph. Both repasses now write the
  recognizer the boxes came from. Measured on the live store: 281 ABO rows
  said the form while naming the caption reader before, 0 after.
- **Secret?** No. The pages are PHI and stay in the local, gitignored store.
- **Blocking now?** Not extraction. Yes for treating a centre-band blood group
  as something a match may rest on, and yes for calling this rule's acceptance
  passed while three placebo gates are failing.
