# AGENTS.md — KidneyMatch Iran

## Mission
Build the project from the repository's versioned specifications. Humans decide policy and provide credentials/judgment; agents implement, test, verify, document, and leave the repo ready for the next session.

## Session start — always
1. Read `docs/agent-memory/CURRENT.md`.
2. Read `docs/work/WORK_QUEUE.json`; work only the requested task or the single `ACTIVE` task.
3. Run `python scripts/doctor.py --brief`.
4. Run `python scripts/context_pack.py --task <TASK_ID>` and read only the returned files first.
5. For complex work, create/update the linked execution plan before editing code.

## Source-of-truth order
1. `docs/product/PRODUCT_CONSTITUTION.md`
2. feature spec in `specs/features/`
3. active execution plan
4. domain policy/docs linked by `docs/index.json`
5. ADRs / architecture docs
6. code + tests
If two higher-priority sources conflict, STOP, record the conflict in `docs/agent-memory/HUMAN_ACTIONS.md`, and ask the human. Do not choose one silently.

## Implementation rules
- Test-first for domain, security, ingestion, OCR, and matching rules.
- Make the smallest coherent change that satisfies the active spec.
- Prefer existing framework/OSS capabilities; never add a dependency without updating the OSS register and lockfile.
- Do not weaken tests to obtain green CI unless a versioned spec/policy changed.
- No real PII/medical data in source control, prompts, fixtures, screenshots, traces, or logs.
- Historical raw inputs are immutable and local-only.
- Every derived medical fact must preserve provenance back to source message/document/crop.
- OCR produces proposals, never laboratory verification.
- Geometry/template cell defines HLA locus; OCR text alone may not assign locus.
- Never infer high-resolution HLA from low-resolution typing.
- Use the highest-quality asset physically available. If only a thumbnail exists, record `THUMBNAIL_ONLY`; never hallucinate or wait indefinitely for a missing original.
- Ambiguous critical OCR => `REVIEW_REQUIRED`, never best-guess acceptance.
- Missing clinical values are `UNKNOWN`, not zero mismatch or compatible.
- Matching is deterministic/versioned and must not read compensation data.
- No LLM may make the final compatibility, fraud, identity, or laboratory-verification finding.

## Human/credential protocol
- Never guess, fabricate, scrape, echo, or commit credentials/secrets.
- Run `python scripts/doctor.py`; it prints exact missing variable/action names.
- Add unresolved human work to `docs/agent-memory/HUMAN_ACTIONS.md` using the supplied template.
- Ask only for the minimum credential or irreversible human decision that blocks the current path; continue independent work when possible.
- Secret values live in ignored `.env`/secret stores, never in Markdown or memory files.

## Verification before completion
Run `python scripts/verify_repo.py` (8 mandatory steps, identical to CI, nothing skipped). For changed behavior, also run the task's acceptance command.

Completion is gated, not asserted:
1. `python scripts/acceptance.py run <TASK>` — runs the acceptance commands and writes evidence to `.artifacts/<TASK>/`.
2. `python scripts/acceptance.py mark <TASK> <N> --evidence <log>` — a criterion cannot be marked met without a real, non-empty evidence file.
3. `python scripts/taskctl.py set <TASK> COMPLETE` — refuses unless every criterion is met with existing evidence, and re-runs the acceptance commands rather than trusting the ledger.

`docs/work/acceptance.json` starts every criterion at `false` and must not be edited by hand; a hook blocks that. Never use `--force` to unblock yourself — it is a human override.

## Operator controls
- `AGENT_STOP` at the repo root halts every tool call. Do not delete it; stop and report to the user.
- `STEER.md` delivers a one-shot operator message, then clears itself. Treat it as higher priority than your current plan.
See `docs/agent-harness/OPERATOR_CONTROLS.md`.

## Long-running work and memory
- Durable facts belong in code/specs/ADRs/docs, not chat history.
- `docs/agent-memory/CURRENT.md` is a short handoff index, not an encyclopedia.
- Update `CURRENT.md`, `KNOWN_ISSUES.md`, and an archived handoff with `python scripts/handoff.py` before ending a substantial session.
- Git history + execution plans + handoffs are the cross-agent memory system; Claude auto-memory is secondary and must not contain secrets or contradict repo memory.

## Review discipline
For high-risk code (matching, HLA, OCR acceptance, auth, trust/safety, document access), use a separate skeptical review pass/session after implementation. The reviewer should look for counterexamples and missing tests before approving.

## Parallel work
Parallelize only independent read-only research or disjoint modules. Use separate worktrees/branches for concurrent editors. Never have two agents edit the same files simultaneously.

## Keep context small
Do not load the consolidated technical bible by default. Follow `docs/INDEX.md`, context packs, nested instructions, and skills. Prefer concise command output; write verbose reports to `.artifacts/`.
