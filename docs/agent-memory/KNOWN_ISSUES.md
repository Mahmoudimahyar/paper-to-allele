# Known issues

Use one issue per heading. Remove or move to an ADR/tech-debt plan when resolved.

## KI-001 — OCR dependency pins are not frozen yet
PaddleOCR/PaddlePaddle, Surya, and OS-level Tesseract behavior must be benchmarked on the actual low-resolution archive before production pinning. This does not block message parsing/dedup.

## KI-002 — Telegram JSON stable sender IDs may not be available
HTML provides message IDs/display names/forward metadata but may not provide stable numeric actor IDs. JSON export can improve identity linkage if available; MVP-HIST must function without it.

## KI-003 — Historical records are unclaimed evidence
Historical candidates are not active platform users and must not be presented as verified/available donors merely because a phone number/report appears in the archive.

## KI-004 — Matching weights are a versioned project heuristic
The DQ/DR-prioritized V1 heuristic is documented but is not a universal clinical standard. It must remain explainable/versioned and later be reviewed/calibrated with Iranian clinical experts/outcomes.

## KI-005 — Harness findings reported but not adversarially verified
The P1 adversarial audit (2026-09-01) reported 31 findings and verified 23
before it was stopped. All 5 confirmed findings were fixed. The following were
reported but never reached a verdict, and are worth a look during P2. Treat them
as unverified claims, not facts:

- ~~acceptance commands run with no subprocess timeout~~ **FIXED**: 900s
  timeout, and both a timeout and an unrunnable command now write FAILED
  evidence rather than raising;
- `shlex.split` may mangle Windows paths in acceptance commands — still open;
- ~~`stop_checkpoint.sh` on a detached HEAD~~ **FIXED**: it now refuses and says
  so, rather than creating a commit git would garbage-collect;
- ~~`stop_checkpoint.sh` leaves the index staged when a commit fails~~
  **FIXED**: the index is reset;
- `post_edit_check.sh` extracts `file_path` with `sed`, so JSON escaping and
  MultiEdit-shaped payloads are not handled;
- ~~`permissions.allow` omits commands a normal TDD loop needs~~ **FIXED**:
  26 rules added (file inspection, search, `python -c/-m`, coverage, bandit,
  mutmut, pre-commit, uv add/lock/export, git worktree/restore). `just` and
  `make` remain allow-listed but are not installed on the dev machine;
- per-tool-call hook latency (~140ms, ~370ms on Edit/Write/Bash);
- acceptance evidence lives in gitignored `.artifacts/`, so a criterion marked
  on one machine cannot be completed from a fresh clone without re-running.

## KI-006 — Enforcement cannot detect a tautological test
The COMPLETE gate proves a task's acceptance command exits 0 and that a criterion
was marked from a passing run of that task. Nothing mechanical distinguishes a
test that proves a criterion from one that asserts a tautology, and an agent may
also shrink the definition of done by deleting acceptance bullets from a spec
(`spec_lint` checks ownership, not that the set has not shrunk). The independent
review pass in `AGENTS.md` is therefore load-bearing, not optional.
See `docs/agent-harness/OPERATOR_CONTROLS.md` section 6.

## KI-007 — Media quality is keyed on filename, which never fires on the real archive
`resolve_best_available_media` assigns `THUMBNAIL_ONLY` from a `_thumb` filename
or a missing original. The real export has **zero** thumbnail-only assets, so
every one of its 145,697 photos would be classified `HIGH_RES_AVAILABLE` -
including the 77% whose longest edge is ~520 px. Low-resolution critical values
would therefore skip the mandatory review the product constitution requires.

Quality must be derived from pixel dimensions. The threshold is a clinical
decision: see `HUMAN_ACTIONS.md` HA-003. Evidence:
`docs/ingestion/ARCHIVE_CHARACTERIZATION_2026-08-31.md`.

Note the existing code is not *wrong* about the case it handles - a missing
original really should degrade quality - it is that the case does not occur here,
so the rule needs a second, dimension-based arm.

## KI-008 — OCR_IMAGE_REVIEW_2026-08-31 generalized from 10 samples
Its resolution finding ("around 520 px") is confirmed at scale, but its
explanation - that the archive supplies thumbnails whose originals are missing -
is not what the export contains. Read it for the per-image failure modes, which
remain valuable, and read the characterization document for the population
figures.

## KI-009 — Thumbnail copies contaminated every derived artefact (FIXED 2026-09-02)
The export contains `photo_N@date_thumb (n).jpg` copies (113,008 files). The
manifest filter in `scripts/ocr_pass.py` tested `endswith("_thumb.jpg")`, so
9,581 of them entered the OCR pass as "unique originals" — 29% of it, the entire
"≤560 px tail", 1,164 Persian-pass rows, 373 template-family members and 54 of
199 golden-sample documents. Every one has its original on disk. True corpus:
**23,566 unique originals, 90% >900 px, 85 at ≤560 px.** Filter fixed
(`is_original_photo`, tested); the sqlite rows are kept as evidence and must be
excluded by `rel_path LIKE '%_thumb%'`; golden sample and template families must
be regenerated. Review: `docs/ingestion/ACCURACY_REVIEW_AND_PLAN_2026-09-02.md`.

## KI-010 — Resolver bound the next row's label as the value (FIXED 2026-09-02)
Under the `below` rule, of 2,977 DRB1 RESOLVED bindings only 185 were
value-shaped and 988 were the next locus label; DPA1/DPB1 had zero value-shaped
bindings. The 34–44% "resolve rates" in `OCR_ENGINE_BENCHMARK_2026-09-01.md`
are superseded. Root causes: no value-shape gate, wrong default direction (the
dominant form is a vertical stack of row labels with values to the right), and
the recognizer reading the trailing `1` of locus labels as `I` (60,995 boxes) and
`DRB5` as `DRBS`, which hid 4.6–7.7× of the anchors. Values: 20.7% of allele
boxes carry a letter in a digit slot (`II`=11, `LS`=15), `*` read as `+ ° - "`.
**FIXED** by ADR 0008: four binding gates, overlap alignment, and a bounded
glyph repair. Documents with 3+ locus anchors rose 3,873 -> 17,041; A/B/DRB1/DQB1
now resolve on 9,411-10,967 documents each with every gate on. CTC logit masking
at decode time (ADR 0006) is still the stronger remedy and is NOT done — it
would fix errors a post-hoc repair cannot, namely a glyph that decodes to a
valid but wrong digit.

## KI-011 — py-ard is 1.5.5, not 2.4.0; IMGT 3650 does not load
`pyproject.toml` pins `py-ard>=1,<2`; the lock resolves 1.5.5. `init(imgt_version="3650")`
raises `IndexError`; `"3620"` loads. `ard.validate("DRB1*11")` rejects
first-field-only alleles by design, so per-locus first-field vocabularies must be
derived from the allele table. The spec's 3.65 pin is unimplementable as locked:
HA-006.

## KI-012 — No extracted value has been compared to a human reading
Every figure in ADR 0008 is a yield or an internal-consistency rate. The strongest
external checks available today are indirect: the DRB1 haplotype constraint agrees
with the grouped DRB3/4/5 row on 99.62% of documents where both were read, and the
anchored ABO distribution matches the Iranian population. Neither measures
wrong-locus false acceptance, which is the failure the project exists to prevent.
The golden corpus is drawn (199 documents, thumbnail-free, all five verified
families) and **unlabelled**. `OCR-001` must stay `BLOCKED_BY_BENCHMARK` until it
is labelled. Nothing extracted so far may be published to Gold.

## KI-013 — These laboratories do not type DQA1, DPA1 or DPB1
Measured over 23,485 documents: the forms print a DPB1 row and leave its cell
empty on 12,739 of the 12,770 documents that carry the label; DPA1 12,595 of
12,626; DQA1 11,284; C 10,833. Under the same rule DRB1's cell is empty on 3,662
of 13,362. This is the laboratory not performing the test, not a rule failure.
Consequence: the archive supports DR/DQB-prioritised matching (KI-004) and cannot
support DP matching at all. `MATCH-HLA-001` must treat DP as structurally UNKNOWN
for historical records rather than as missing data to chase.

## KI-014 — The dominant letterhead disclaims its own blood-group field
The Yekta form prints "information regarding the blood group is based on the
attendee's own account, and the laboratory bears no responsibility for its
accuracy" — 2,928 documents, 97.7% of them carrying the Yekta marker. A printed
ABO from that family is `PATIENT_REPORTED_ON_FORM`, not a laboratory measurement,
and its agreement with the caption is not independent corroboration because both
can descend from the same statement. `MATCH-ABO-001` must not accept it as a
verified blood group.

## KI-015 — Single resolved allele read as complete (FIXED 2026-09-02)
Found by the skeptical review of ADR 0008 (`docs/ingestion/EXTRACTION_REVIEW_2026-09-02.md`,
W1). In two-allele cells the gap to the second allele is median 15.3 label heights,
p90 18.4, max exactly 20.0 — the cap. 6,597 single-allele cells have the
heterozygous second allele just beyond the chain (self-prefixed with the same locus
in 98–99% of cases). 29–36% of resolved A/B/DRB1 cells are single-allele, far above
any homozygosity rate, and `LocusResolution` cannot say whether one allele was
printed or one was read. Any consumer treating a single value as homozygous will
miscount every mismatch. **FIXED**: `LocusResolution` carries `SecondAllele.READ`/`UNREAD` and there is no
way to get a value list without it; any aligned value-shaped box beyond the chain
forces review (7,055 cells). The gap must still be validated against the golden
corpus rather than tuned by yield.

## KI-016 — No first-field admissibility gate (FIXED 2026-09-02)
480 resolved values (0.64%) carry a first field that does not exist for their locus,
mostly a leading `0` read as `8`/`9` with clean digits (`A*83`, `C*84`, `DQB1*83`,
`DRB1*93/97`), which glyph repair cannot see. **FIXED**: a fifth gate reads `config/hla_first_fields.json`, generated by
`scripts/build_hla_vocabulary.py` from IMGT 3620 and committed with its release
stamped inside. Nomenclature-impossible resolved values went 480 → 0. The gate
fails loudly if the table is missing rather than degrading to accept-everything.

## KI-017 — Review findings against ADR 0008: wrong-fact classes closed, P1-P6 open
The review raised 42 findings; 39 survived three-refuter verification, 16 able to
emit a wrong fact (KI-015, KI-016, a value box bound to two loci, a recipient regex
matching the verb `کرده` on 2,062 documents, a choice label read as DONOR,
comparison sheets resolving two people's cells, the grouped row's centre band, the
wrapped ABO disclaimer). The consistency check's 99.62% is the two-value subset:
one-value DRB1 rows are doubled and manufacture 1,315 false flags. The ranked fix
plan is section 4 of the review. Nothing extracted may be published (KI-012 stands).
**Status 2026-09-02:** P0-P5 and P7 done (ADR 0009 and its amendment); P6 open (KI-018).

## KI-018 — The 4,944 documents that yield nothing are mostly not reports
7,516 documents produced no fact. 2,572 of them anchored a locus label and had
every cell refused (multi-column layouts, "N candidates", "2 anchors"). The
other 4,944 anchored nothing at all, and an earlier note here blamed forms that
print class I loci without the `HLA-` prefix. **That was wrong, and the
correction shrinks the work by an order of magnitude.**

Measured 2026-09-02 against the 16,050 documents that did produce facts:

| signal | produced facts | anchored nothing |
|---|---:|---:|
| carries a canonical locus label | 98.9% | 9.0% |
| carries ≥1 allele with a star or colon | 98.6% | 27.8% |
| carries ≥4 such alleles | 95.0% | 9.3% |
| carries ≥8 such alleles | 63.6% | 6.1% |

A bare `A` box, the shape the earlier note named, is **less** common in the
failing group (1.8% of documents carry three or more) than in the working one
(3.2%): it is background noise present in both, not a missing label. The
failing documents do not lack labels while holding values; **72% hold no
allele-shaped value either**, and 8.5% carry almost no text at all. They are
photographs, screenshots, chat images and other non-reports.

Only **170** documents carry both a canonical label and four or more starred
alleles, and the labels they carry are DRB3/DRB4/DRB5 (127/41/71) with almost
no A, B, C, DRB1 or DQB1 — the grouped DRBX row was read and the main rows were
not. That is the real P6 target and it is a few hundred documents, not
thousands.

**Consequence for the plan.** The recoverable corpus is close to what is already
extracted. Effort belongs on validating the 16,050 documents that did produce
facts (HA-008, HA-007), not on recovering the rest.
See `docs/ingestion/OPEN_ISSUES_SOLUTIONS_2026-09-02.md` issue 6c.

## KI-019 — Tesseract has no opinion on half the class I cells
On FORM#1 the class I value box is 57% the width of a class II box (`A*02` is
four glyphs). Tesseract returns nothing on 19-32% of those crops and a star-less
string on most of the rest. The star-less parse (2026-09-02) moved 2,356 cells
to CONFIRMED and 162 out of CONTRADICTED over the stored readings; 18,019 cells
still had no second opinion. **CLOSED 2026-09-03.** PP-OCRv5 en-mobile-rec was
adopted as a second confirmer (`--extra confirm`) and run over all 47,221
resolved cells: 43,124 confirmed / 3,063 contradicted / 1,034 no opinion, and it
answers on **17,206 of the cells Tesseract could not read**.

The adoption nearly went wrong, and the reason is worth keeping. The survey
measured single-allele crops; the confirmer's crop spanned both alleles of a
heterozygous cell, and on that crop PP-OCRv5 contradicted the pipeline on 50.7%
of the cells the decode called unanimous AND Tesseract confirmed. A coin flip is
what a mismatched crop looks like. Reading one crop per value box moved that to
97.3% agreement. **A benchmark's crop geometry must match production's**, or its
numbers describe a different task.
See `docs/ingestion/OCR_MODEL_SURVEY_2026-09-03.md`.

## KI-020 — The DOM reference's forwarded snippet cost 37% of the archive its author
`TELEGRAM_HTML_EXPORT_STRUCTURE.md` showed a forwarded message as the avatar
column plus `div.forwarded.body`, and a parser written from it replaced the
message body with the forwarded block. In the real export that block is nested
INSIDE the message's own `body`, which carries the current poster's `from_name`
and the posting time — so the current poster was never read and the sender was
inherited from whichever message came before. That is wrong attribution on
65,127 messages.

Caught by running against the real archive and asking why 97.2% of forwarded
messages had an inherited sender when only 7.4% were joined. After the fix,
inherited senders equal the joined count exactly (13,429), which is the only
case the exporter's own rule allows. FIXED 2026-09-03; the reference and the
synthetic fixture now match what the export emits.

**The general lesson:** a synthetic fixture built from a doc inherits the doc's
errors, and only real input finds them. Every structural claim about the export
should be re-checked against the archive once, cheaply, before it is trusted.

## KI-021 — The labelling page asked three questions about one printed row (FIXED 2026-09-05)
The review pack rendered DRB3, DRB4 and DRB5 as three cells each demanding
"two alleles". The form prints that row as gene NAMES (22,017 gene tokens
against 75 bare numbers corpus-wide), so the reviewer typed 03/04/05 — the
digit of the printed name — into every one of the 17 DRB3/4/5 "values" of the
first 165 labels, and copied the same number into two or three genes on five
documents. Seventeen of nineteen "contradictions" were this artefact. The page
now asks the row's question — which genes are printed — and derives the
per-gene labels; labels made under the old question render as "re-confirm".
Those 45 DRB3/4/5 labels in the reviewer's first export are not ground truth and
must be re-confirmed. `docs/ingestion/CV_RESEARCH_2026-09-05.md` §1.

## KI-022 — The recognizer drops the `*` and the value was refused for it (FIXED 2026-09-05)
3,153 cells corpus-wide were refused only because `A*02` had been read `A02`
— 45% of every shape refusal, 6 of the reviewer's 21 misses. The parser now
accepts a prefix that names a locus followed by two or three digits, marks the
missing star as a repair, and repairs the B/8 prefix confusion when a star
follows. Corpus: +2,368 cells resolved, 46 moved the other way (all the KI-015
second-allele guard), 0 changed values. Still open in the same family: 896
prefixed values with a damaged prefix (`DRIL*##`) and 4,088 other shape
refusals; the constrained decode already reads many of them (`PROPOSAL`), and
the golden corpus decides whether a proposal may ever be promoted.

## KI-023 — Three OpenCV wheels are in the lockfile
`uv.lock` resolves `opencv-python-headless` (pinned in `pyproject.toml`),
`opencv-python` 5.0 (through onnxtr) and `opencv-contrib-python` 4.10 into one
environment; PyPI warns only one may be installed, and which `cv2` imports is
whichever landed last (4.14 headless today). `cv2.createLineSegmentDetector`
lives in the main module since 4.5.1, so nothing needs contrib. Resolve to one
wheel with a `uv lock` and an OSS-register row; no behaviour depends on it yet.

## KI-024 — Below 1.5 degrees the page frame is a wash
On the review pack's 53 ROTATE pages the levelled frame gained and lost cells
in equal numbers under 1.5° of tilt (9 each): the row rules already tolerate
that drift and the estimators' own error is as large as the tilt. From 2° it
gained 5 and lost none. The extraction therefore applies the frame from 1.5°
(`extract_facts.MIN_FRAME_TILT_DEG`); the geometry pass still records ROTATE
from 0.5° as measurement. Revisit with the crop-level rotation (M4), which is
where small tilts actually cost recognition.

Corpus-wide (2026-09-05, 1,205 levelled pages): 1,121 cells gained, 97 lost,
and 168 resolved cells changed value — every one of them a second allele gained
(140) or dropped (28), never an allele swapped for another. The 28 drops are
on pages tilted 2-4°; 24 of the dropped alleles belong to no other locus on the
page, so they are most likely real second alleles the de-inflation pushed out of
the row band on wide rows. Experiment: level the centres without de-inflating
the hulls and count whether the 28 return without the 140 leaving.
