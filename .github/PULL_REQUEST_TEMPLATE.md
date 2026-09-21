## What and why

<!-- What changes, and what problem it solves. Link the issue or task id. -->

## How it was verified

<!-- Paste the relevant output, or name the tests that now cover this. -->

- [ ] `uv run --frozen python scripts/verify_repo.py` passes (12 steps, none skipped)
- [ ] A failing test was written first, and it now passes

## Safety checklist

- [ ] No real personal or medical data in code, tests, fixtures, logs or screenshots
- [ ] No missing clinical value coerced to zero, compatible, or a default
- [ ] No locus assigned from OCR text alone, outside the documented exceptions
- [ ] No test weakened or removed; if one changed, the spec or policy change is linked
- [ ] Any new decision pass is dry-run by default and can be undone

## Risk

<!-- Delete what does not apply. -->

- Risk level: low / medium / **high** (matching, HLA, OCR acceptance, auth, document access)
- High-risk changes need an independent sceptical review before merge.

## Documentation

- [ ] ADR added or updated, if this was an architectural decision
- [ ] Measurement reproducible by a script, if this PR quotes numbers
- [ ] Known issues updated, if this leaves something knowingly unfixed
