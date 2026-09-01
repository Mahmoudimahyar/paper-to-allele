# Harness readiness review — 2026-09-01

**Reviewer:** Claude (Opus 5) · **Scope:** whole repository, before first product task
**Verdict:** the *design* is strong; the *mechanism* is not yet built. Fix P0/P1 before the first long autonomous run.

## Evidence baseline (commands actually run)

| Command | Result |
|---|---|
| `git rev-parse --is-inside-work-tree` | **fatal: not a git repository** |
| `python scripts/doctor.py --brief` | prints `HUMAN ACTION REQUIRED` on every run (py3.13 vs pin `<3.13`) |
| `python scripts/verify_repo.py` | **FAIL** at `ruff check .` |
| `ruff check .` | **26 errors** (16 I001, 8 E501, 1 E401, 1 UP017) |
| `ruff format --check .` | **13 files would be reformatted** |
| `mypy src` | PASS (19 files) |
| `pytest -q` | 10 passed |

Work-queue integrity: 42 tasks · 10 have a spec · **1 has machine-checkable acceptance** · 1 has a plan · `MEDIA-001` and `DEDUPE-001` point at the *same* spec file. Test dirs `e2e/ integration/ ocr/ property/` are empty.

---

## What is already right — do not rebuild it

1. Short root `AGENTS.md` + `CLAUDE.md` importing it; nested per-package `AGENTS.md`/`CLAUDE.md`; `.claude/rules/` with `paths:` frontmatter (verified as a currently supported Claude Code mechanism). This is the correct 2026 layout.
2. Progressive disclosure via `docs/index.json` + `scripts/context_pack.py`, with the 1544-line bible explicitly excluded from startup.
3. Skills authored once in `.agents/skills/` and mirrored to `.claude/skills/` with a CI drift check.
4. **The clinical safety invariants are the hardest part of this project and they are done well.** Extraction-confidence vs provenance-trust separation, `UNKNOWN` never collapsing to compatible, geometry-determines-locus, no low→high resolution promotion, matching isolated from compensation with an AST lint enforcing it.
5. `doctor.py` never echoes secrets; the `HUMAN_ACTIONS.md` protocol keeps values out of the repo.

---

## P0 — blockers. The harness cannot do its job until these are fixed.

### P0-1 Not a Git repository
`AGENTS.md` states "Git history + execution plans + handoffs are the cross-agent memory system." One third of that system does not exist. Consequences: `handoff.py` records `NO_GIT_COMMIT`; the independent-reviewer pattern has no diff to review; there is no rollback; the branch/worktree parallelism in `CONTRIBUTING.md` is impossible; a multi-hour run has no checkpoints, so one bad edit loses everything.
**Fix:** run `scripts/init_repo.sh` after setting `git config user.name/user.email`. Do this first.

### P0-2 CI is red on a fresh clone
`.github/workflows/ci.yml` runs `ruff check .` and `ruff format --check .`; both fail today. The first autonomous session will spend its opening context repairing the harness — and worse, an agent told "do not weaken tests to obtain green CI" gets an ambiguous signal from a baseline that was never green.
**Fix:** `ruff check --fix . && ruff format .`, then commit as the green baseline. Add `tests/contracts/test_baseline_is_green.py` asserting the repo ships clean.

### P0-3 Stray `\` line at the top of 10 files
All 9 `scripts/*.py` and `src/kidneymatch/hla/normalize.py` begin with a literal backslash + newline (a ZIP packaging artifact). Python's line-continuation happens to make it parse, but it breaks the `#!` shebang on POSIX, shifts every ruff/mypy line number by one, and will confuse an agent reading a traceback.
**Fix:** strip the first line from those 10 files.

### P0-4 Python version mismatch produces a permanent false alarm
`pyproject` pins `>=3.12,<3.13`; the machine has 3.13.14; there is no `.venv`. `doctor.py` therefore prints `HUMAN ACTION REQUIRED: Install/use Python 3.12` on **every** invocation. An agent that sees the same non-actionable alarm at every session start learns to ignore doctor output entirely — which is exactly the channel reserved for real credential blocks.
**Fix:** either run `bash scripts/bootstrap.sh` to create the 3.12 env and make it the default interpreter, or widen the pin to `<3.14` and re-verify. Then make `doctor.py --brief` exit non-zero *only* on genuine blockers.

### P0-5 No lockfile
`AGENTS.md` forbids adding a dependency "without updating the OSS register **and lockfile**"; no `uv.lock` exists, and CI's `uv sync` re-resolves every run. The rule is unenforceable and builds are not reproducible — unacceptable for a system whose OCR and HLA-reference behavior must be pinned for benchmarks to be comparable across sessions.
**Fix:** commit `uv.lock`; switch CI to `uv sync --frozen`.

---

## P1 — required for "runs for hours without stopping"

The repo documents the long-running-agent discipline but implements none of its machinery. Anthropic's published pattern (planner / generator / **fresh-context evaluator**, communicating through files, gated by hooks) needs five concrete additions here.

### P1-1 No hooks — nothing sits between an instruction and a commit
`.claude/settings.json` is three lines. Instructions are context, not enforcement; hooks are the enforcement layer. Add:
- **PostToolUse** on `Edit|Write` → `ruff check --fix` + `ruff format` on the touched file, and run the focused test file when one exists. Catches breakage in seconds instead of at end-of-session.
- **Stop** → auto-commit a WIP checkpoint (`chore(wip): <task> <timestamp>`) so a crash or context reset never loses work.
- **PreToolUse** on writes to the status ledger → block unless verification evidence was produced (see P1-3).
- **SessionStart** → print `taskctl next` + `doctor --brief` so orientation costs no reasoning tokens.

### P1-2 No permissions allowlist — the agent will stop on prompts
This is the single most direct cause of "the agent stopped." Add to `.claude/settings.json` under `permissions.allow`: `Bash(pytest*)`, `Bash(ruff*)`, `Bash(mypy*)`, `Bash(python scripts/*)`, `Bash(git status*|git diff*|git add*|git commit*|git log*)`, `Bash(uv run*)`, `Bash(just*)`. Keep `permissions.deny` on `data/raw/**`, `.env`, and network egress.

### P1-3 No default-FAIL acceptance ledger
`taskctl.py set <TASK> COMPLETE` writes the status with **no gate whatsoever**. An agent can mark work done without running anything. Anthropic's harness solves this with a contract file where every criterion starts `false` and cannot be flipped until evidence has been read.
**Fix:** add `docs/work/acceptance.json` — one entry per acceptance criterion per task, all `{"passes": false}` — and make `taskctl set ... COMPLETE` refuse unless every criterion for that task is `true` *and* a matching evidence file exists under `.artifacts/<TASK>/`. Have each acceptance command write its exit code and output there.

### P1-4 Only 1 of 42 tasks has a runnable acceptance command
Spec acceptance is prose ("normal/joined/forwarded/reply fixtures parse"). Prose cannot end a loop. Every `READY` task needs at least one command returning 0/non-zero, and `spec_lint.py` should enforce it — otherwise the agent reaches HIST-002 and invents its own definition of done, which is where multi-hour runs silently drift.

### P1-5 No kill-switch or steering channel
Unattended multi-hour runs need out-of-band control: an `AGENT_STOP` sentinel file checked by a hook that halts execution, and a `STEER.md` surfaced once then cleared. Roughly 20 lines; without it the only intervention is Ctrl-C at an arbitrary point.

---

## P2 — testing depth (the largest gap vs. the stated goal)

`TEST_PLAN.md` enumerates ten test layers. **Three exist. Ten tests total, four of them substantive.** The plan is aspiration, not infrastructure. To make "everything is tested" mechanically true rather than asserted:

### P2-1 Invariant → test traceability
Every spec carries an `invariants` array and nothing links them to tests. Add a marker convention — `@pytest.mark.invariant("HIST-001", "re-ingestion is idempotent")` — plus a lint that fails when any `READY`/`ACTIVE` spec invariant has zero covering tests. This converts the requirement into a gate instead of a hope, and is the highest-leverage testing change in this list.

### P2-2 Property-based testing is declared but unused
`hypothesis` is a dependency; `tests/property/` is empty. Published measurement puts a property test at roughly **50× the mutants killed** of an average unit test. Highest-value properties here: HLA normalization round-trips and never gains resolution; parser idempotency under message reordering; media resolution never reports a quality better than the file it actually opened; match ranking is a total order and is invariant under compensation changes.

### P2-3 No mutation testing despite the plan naming it
`TEST_PLAN.md` §2 lists "mutation testing for matching/authorization/consent" — no tool is chosen or installed. Mutation score is the only metric that answers "do my tests catch bugs, or just execute lines." Pick `mutmut` (fast, simple) over `cosmic-ray` at this size, scope it to `matching/`, `hla/`, and OCR acceptance, and put a score threshold in `just release-verify`. Sequence it *after* P2-2, since property tests are what will actually kill the mutants.

### P2-4 Metamorphic tests for OCR — the layer that finds the hard bugs
This is where "issues that are normally hard to find" actually live, and it is absent from the plan. The relations are strong and cheap to assert:
- downscaling or blurring must never *increase* confidence, and must move the result toward **abstain**, never toward a *different* allele;
- re-encoding at lower JPEG quality must not change locus assignment;
- a template rotated within tolerance yields the same cell→locus mapping;
- cropping a non-HLA region cannot change an HLA field's value.
Each catches a class of silent wrong-locus acceptance that no golden test on clean fixtures will ever reach.

### P2-5 The golden corpus is a scheduling landmine
`TEST_PLAN.md` §8 gates the whole OCR phase on "200 manually labelled unique documents" — human work that cannot be committed (real patient data) and cannot be agent-parallelised. `OCR-BENCH-001` will stall MVP-HIST.
**Fix:** build a **synthetic Persian lab-form generator** first — render fake HLA report templates at controlled resolution, blur, JPEG quality, rotation, and occlusion, with known ground truth. That yields an unlimited, committable, fully-labelled corpus for the metamorphic and regression layers, and demotes the human-labelled 200 from prerequisite to final *calibration* set. This unblocks the longest pole in the schedule.

### P2-6 UI testing is deferred to V3+/V5 — too late
`OSS_DEPENDENCIES.md` marks Playwright "ADOPT V3+", but the first place a wrong HLA locus reaches a human is `REVIEW-001`, the human review workflow, in **MVP-HIST**. That screen is safety-critical: a reviewer who cannot see the source crop beside the proposed value will rubber-stamp errors.
**Fix:** pull a minimal review UI forward and test it from day one with Playwright accessibility-tree (`aria`) snapshots — deterministic, no vision model, resilient to DOM churn — plus `axe-core` for WCAG and visual regression on the crop-vs-value panel. Persian RTL layout defects are precisely the hard-to-find class. Add a Playwright trace-scrubbing rule: traces capture screenshots, and a trace of the review UI over real data is a PII leak.

### P2-7 No coverage gate, no determinism check, no security scanning
- `pytest-cov` is installed but unused: add `--cov --cov-fail-under`, holding `matching/` and `hla/` near 100%.
- The matching invariant "same inputs + same policy versions → identical rank" is untested; there is no frozen clock or seeded UUID strategy, though `MatchRun` carries both. Add `pytest-randomly` (order independence) and a run-twice determinism assertion.
- ASVS 5.0 is named as the baseline with no tooling behind it. For a system holding medical PII, add `bandit` or `semgrep`, `pip-audit`, and `gitleaks` to pre-commit and CI **now**, not "when release automation is added."

### P2-8 PII protection is one weak grep
`tests/security/test_no_sensitive_fixture_names.py` greps for the single literal string `data/raw/telegram-export`. That is close to no protection for the highest-severity risk in the project.
**Fix:** a real scanner over `tests/`, `.artifacts/`, and logs for Iranian phone patterns, national-ID checksums, and Persian personal names; an autouse fixture failing any test that writes outside `tmp_path`; and `gitleaks` in pre-commit.

---

## P3 — token efficiency and doc hygiene

- **`context_pack.py` lists paths but does not budget them.** It prints filenames and the agent then reads all of them blind. Add line/byte counts, a running total, and a REQUIRED vs ON_DEMAND split so the agent can stop reading once the budget is met.
- **The 1544-line legacy bible is a correctness trap, not just a token cost.** It is 28% of repo content, is absent from `index.json`, and is marked "do not load" — yet it certainly holds facts missing from the modular docs. When an agent eventually opens it and finds a conflict, the source-of-truth order in `AGENTS.md` gives no ruling on an *unindexed* document. Audit it once: promote anything canonical into the modular docs, then mark each remaining section `SUPERSEDED-BY: <path>`.
- **`spec_lint.py` re-implements a subset of `schemas/feature_spec.schema.json` by hand** instead of validating against it. The schema is dead code today and will drift; `schemas/field_claim.schema.json` is unused entirely.
- **`docs_lint.py` checks index→file but not file→index.** Orphans today: `ARCHITECTURE.md`, `DATA_MODEL.md`, `BOOTSTRAP.md`, `TELEGRAM_V2_V4.md`, `OCR_IMAGE_REVIEW`, `PROJECT_REFERENCES`, the bible. Add reverse-coverage and markdown link-rot checks.
- **`MEDIA-001` and `DEDUPE-001` share one spec file.** Either split them or merge the tasks; two tasks under one contract makes "done" ambiguous for both.

---

## Recommended sequence before the first product commit

1. **P0 batch** (~1 session): git init → strip stray `\` lines → `ruff --fix` + format → resolve the 3.12/3.13 pin → commit `uv.lock`. End state: `python scripts/verify_repo.py` is green, and that green state is the first commit.
2. **P1 batch** (~1 session): hooks, permissions allowlist, `acceptance.json` default-FAIL ledger with a gated `taskctl`, `AGENT_STOP`/`STEER.md`, machine-checkable acceptance on every `READY` task.
3. **P2-1 + P2-2** before any feature code: invariant markers with the coverage lint, and the first property tests against the code that already exists (`normalize_reported_hla`, `resolve_best_available_media`). This proves the TDD loop end-to-end on a small surface before it has to carry OCR.
4. **P2-5 synthetic corpus generator** — schedule early; it is the longest pole and all OCR work depends on it.
5. Then start `HIST-001`.

Steps 1–3 are roughly two focused sessions and convert the harness from well-designed to operational. Starting `HIST-001` before them means the first autonomous run spends its context fixing the harness, on a red baseline, with no git history to roll back to.

## Sources consulted
- Anthropic, *Harness design for long-running application development* (2026-03-24)
- Anthropic, `anthropics/cwc-long-running-agents` reference implementation (default-FAIL contract; verify-gate / commit-on-stop / kill-switch hooks; fresh-context evaluator)
- Claude Code documentation — project memory, `.claude/rules/` path scoping, hooks
- *An Empirical Evaluation of Property-Based Testing in Python*, PACMPL (property tests ≈50× mutants killed vs. unit tests)
- Playwright test agents + MCP accessibility-tree snapshots; `axe-core` WCAG assertions
