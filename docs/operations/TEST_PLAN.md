# TDD and Verification Plan

## 1. Coding philosophy
Tests are executable product specifications. Critical rules are written as failing tests before implementation.

## 2. Test layers
- unit
- property-based
- parser golden tests
- OCR golden tests
- DB constraint tests
- integration
- acceptance/Gherkin
- permissions/security
- end-to-end
- backup/restore
- mutation testing for matching/authorization/consent

## 3. Historical parser invariants
- same export imported twice creates zero duplicate messages;
- joined message inherits correct structural context;
- forwarded current sender and forwarded sender remain distinct;
- reply target links without accidental bundle merge;
- same original media path references one MediaAsset;
- same SHA256 references one binary asset;
- repeated source messages are preserved.

## 4. OCR invariants
- thumbnail cannot auto-publish HLA to Gold;
- HLA-B cell cannot populate DQB1;
- DQB1 cell cannot populate HLA-B;
- invalid HLA nomenclature requires review;
- low-resolution value is never upgraded to high-resolution;
- OCR disagreement requires review;
- caption/document conflict requires review;
- DRB3/4/5 stored separately;
- every Gold HLA field has source/crop provenance;
- model upgrade may not worsen wrong-locus false acceptance.

## 5. Dedup/entity invariants
- same HLA different people never auto-merge;
- same phone alone never hard-merges people;
- exact report ID + same lab may create strong duplicate candidate but still preserves sources;
- fraud allegation does not automatically mark confirmed fraud.

## 6. Matching invariants
- ABO unknown never passes compatible;
- positive physical crossmatch blocks ordinary direct ranking;
- known DSA/unacceptable antigen against donor cannot be ignored by HLA score;
- missing locus is UNKNOWN, not zero mismatch;
- changing compensation does not alter rank;
- matching core cannot import/query compensation;
- DQ priority outranks B/A/C when otherwise clinically comparable according to policy;
- same inputs + same policy/reference versions → identical rank;
- high-res DQ algorithm never runs on low-res-only typing.

## 7. V3/V4 security invariants
- one normal account cannot create two active people;
- multiple documents allowed only for same person; identity conflict pauses profile;
- recipient cannot browse matches before completeness gate;
- donor cannot see full recipient list;
- connection requires mutual action;
- all disclosure is audited;
- no payment/counteroffer endpoint exists.

## 8. Golden OCR acceptance targets
Before processing full corpus:
- 200 manually labelled unique documents minimum;
- 100% correct locus association after human-review workflow;
- automated wrong-locus false acceptance: 0 on golden set;
- critical-field auto-proposal precision target >= 99.5%; if not met, raise abstention threshold;
- all remaining uncertainty routed to review.

The system optimizes for precision and safe abstention, not maximum automation.

## 9. Commands

| Command | What it runs |
|---|---|
| `just lint` | docs/spec/architecture/invariant lints, ruff check + format |
| `just types` | mypy |
| `just unit` | unit + contract tests |
| `just security` | Iranian PII scan, bandit |
| `just audit` | osv-scanner against `uv.lock` |
| `just verify` | **the gate** - 12 mandatory steps, identical to CI, nothing skipped |
| `just accept <TASK>` | that task's acceptance commands, writing evidence |
| `just verify-mutation` | mutmut + threshold gate (**Linux/WSL only**: mutmut uses `os.fork()`) |

## 10. Current state (2026-09-01)

Layers that exist, with counts, so this document cannot drift into fiction:

| Layer | Status |
|---|---|
| unit | yes - `tests/unit` |
| contract / repo-invariant | yes - `tests/contracts` (harness, hooks, acceptance gate) |
| property-based | yes - `tests/property`, Hypothesis |
| integration | yes - `tests/integration`, against the synthetic export fixture |
| security / privacy | yes - `tests/security`, PII scanner with checksum |
| coverage gate | yes - repo ratchet 65%, medical modules 100% |
| mutation | configured (`[tool.mutmut]`, `scripts/mutation_gate.py`), CI job present |
| invariant traceability | yes - `scripts/invariant_lint.py`, enforced at task COMPLETE |
| OCR golden / metamorphic | **not yet** - blocked on the synthetic lab-form generator |
| Gherkin / acceptance BDD | **not yet** |
| DB constraint | **not yet** - no database layer yet |
| end-to-end / UI (Playwright, axe) | **not yet** - no UI yet; see P2-6 |
| backup/restore | **not yet** |

The gaps are real and deliberate: each is blocked on code that does not exist.
Do not mark this section complete without adding the corresponding tests.
