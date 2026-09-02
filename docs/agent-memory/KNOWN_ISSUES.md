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
