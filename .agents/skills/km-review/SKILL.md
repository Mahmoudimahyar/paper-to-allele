---
name: km-review
description: Perform an independent skeptical review of a KidneyMatch change. Use for high-risk or merge-ready work; prioritize defects and missing tests over praise.
---

# Independent review
Read the spec, diff, and test evidence without relying on the implementer's reasoning transcript.
Search for: policy contradiction, wrong UNKNOWN handling, silent fallback, provenance loss, authorization leak, PII/log leakage, non-idempotency, bad rollback, missing negative tests, dependency drift, and matching/compensation coupling.
Return findings ordered by severity with file/line pointers when possible. If no finding, list the adversarial cases actually checked.
