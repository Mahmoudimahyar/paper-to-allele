---
name: km-matching-review
description: Design, implement, or review the kidney matching/ranking core. Use only for V1-MATCH or later clinical pre-screen logic.
---

# Matching safety workflow
Read `docs/clinical/MATCHING_POLICY_V1.md` and `config/matching_policy_ir_v1.json`.
Hard gates precede HLA tie-breakers. Missing values are UNKNOWN. No compatibility percentage. Matching is deterministic/versioned. The matching package must not import/read compensation. Low-resolution HLA cannot become high-resolution through imputation. Any new clinical weighting requires a policy version change and supporting evidence/review.
