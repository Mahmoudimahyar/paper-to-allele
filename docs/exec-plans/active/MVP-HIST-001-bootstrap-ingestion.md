# HIST-001 — Parse Telegram HTML into immutable source records

**Status:** ACTIVE
**Feature spec:** `specs/features/HIST-001-telegram-html-ingestion.json`
**Phase:** MVP-HIST

## Objective
Build an idempotent parser that converts Telegram Desktop HTML exports into source message/media-reference records without OCR or person/candidate inference.

## Non-goals
- OCR/HLA extraction.
- entity/person merge.
- fraud finding.
- matching.
- contacting people.

## Invariants
- `message<ID>` is a message ID, not a Telegram user ID.
- current sender and forwarded sender are distinct fields.
- joined messages inherit structural sender/bundle context only according to the spec; do not guess subject identity.
- raw text is preserved; normalized text is a separate derived field.
- phone/username links are evidence claims, not verified identity.
- repeated ingestion is idempotent.

## Milestones
- [x] Define synthetic HTML fixtures for normal, joined, forwarded, reply, image-only, text-only and service messages.
      `tests/fixtures/synthetic/telegram_export/`, structure documented in
      `docs/ingestion/TELEGRAM_HTML_EXPORT_STRUCTURE.md`, guarded by
      `tests/integration/test_synthetic_export_fixture.py`.
- [ ] Parse stable fields with no third-party dependency requirement in the test core or with a pinned HTML parser after spike.
- [ ] Preserve unknown/unparsed fragments for forensic review.
- [ ] Add idempotency contract and parser-version field.
- [ ] Produce concise inventory output.

## Acceptance commands
```bash
uv run --frozen pytest --task HIST-001 -q   # the task's acceptance command
python scripts/verify_repo.py              # the repo gate, 12 steps
```

HIST-001 owns five spec invariants, none of which has a covering test yet.
`python scripts/taskctl.py set HIST-001 COMPLETE` will refuse until each has one
(`python scripts/invariant_lint.py` lists them).

## Progress log
- 2026-09-01: starter repository and contract created; implementation intentionally minimal.
- 2026-09-01: P0/P1/P2 harness work complete. Synthetic fixture corpus and the
  Telegram DOM reference are in place, so implementation can start test-first
  against realistic input without any real archive.

## Rollback
Parser is append-only at the evidence layer. Rollback the parser version/code; never mutate raw archive files.
