---
paths:
  - "src/kidneymatch/web/**/*.py"
  - "src/kidneymatch/trust_safety/**/*.py"
  - "src/kidneymatch/documents/**/*.py"
---
# Sensitive-data path rules
- Deny by default; object authorization must be server-side.
- No real PII/health/genetic data in logs or test artifacts.
- Secret values are never printed or committed.
- Prefer narrow role-specific data access over administrator-wide access.
