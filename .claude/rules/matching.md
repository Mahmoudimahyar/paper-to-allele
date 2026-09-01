---
paths:
  - "src/kidneymatch/matching/**/*.py"
  - "tests/**/*matching*.py"
---
# Matching path rules
- Load `km-matching-review`.
- No compensation import or query.
- Hard gates precede HLA heuristic ranking.
- UNKNOWN cannot be coerced to zero mismatch or compatible.
- Every result must carry policy/input version information when implementation reaches V1.
