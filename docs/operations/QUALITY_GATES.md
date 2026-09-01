# Quality gates

## Every pull request
- instruction/skill sync check;
- docs/spec/architecture lints;
- Ruff + formatting;
- mypy when environment installed;
- unit/contract tests;
- changed-feature acceptance tests;
- no real-data fixtures.

## High-risk feature
Additionally:
- property/adversarial tests;
- independent skeptical review;
- provenance/UNKNOWN-state review;
- authorization/privacy negative tests;
- rollback documented;
- policy version changed when behavior meaningfully changes.

## Release gates
- golden OCR benchmark for OCR changes;
- full backup/restore test for data-layer releases;
- security requirement traceability (OWASP ASVS 5.0 baseline for web phase);
- dependency/license/SBOM scan when release automation is added.
