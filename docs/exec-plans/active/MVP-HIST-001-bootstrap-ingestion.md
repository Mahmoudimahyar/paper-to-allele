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
- [ ] Define synthetic HTML fixtures for normal, joined, forwarded, reply, image-only, text-only and service messages.
- [ ] Parse stable fields with no third-party dependency requirement in the test core or with a pinned HTML parser after spike.
- [ ] Preserve unknown/unparsed fragments for forensic review.
- [ ] Add idempotency contract and parser-version field.
- [ ] Produce concise inventory output.

## Acceptance commands
```bash
pytest tests/unit tests/contracts -q
python scripts/spec_lint.py
python scripts/docs_lint.py
python scripts/architecture_lint.py
```

## Progress log
- 2026-09-01: starter repository and contract created; implementation intentionally minimal.

## Rollback
Parser is append-only at the evidence layer. Rollback the parser version/code; never mutate raw archive files.
