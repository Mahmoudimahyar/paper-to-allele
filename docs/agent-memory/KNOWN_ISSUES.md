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

- acceptance commands run with no subprocess timeout, so a hung command stalls
  an unattended run (`scripts/acceptance.py`);
- `shlex.split` may mangle Windows paths in acceptance commands;
- `stop_checkpoint.sh` on a detached HEAD would commit onto the detached HEAD,
  producing a commit git will eventually garbage-collect;
- `stop_checkpoint.sh` leaves the index staged when a commit fails;
- `post_edit_check.sh` extracts `file_path` with `sed`, so JSON escaping and
  MultiEdit-shaped payloads are not handled;
- `permissions.allow` may omit commands a normal TDD loop needs; `just` and
  `make` are allow-listed but neither is installed here;
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
