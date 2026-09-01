---
paths:
  - "src/kidneymatch/ocr/**/*.py"
  - "src/kidneymatch/hla/**/*.py"
  - "tests/ocr/**/*.py"
---
# OCR/HLA path rules
- Read the `km-ocr-benchmark` skill before changing extraction acceptance behavior.
- Never assign HLA locus from recognized token text alone; the expected cell/locus is an input.
- Preserve engine disagreements and abstain on ambiguity.
- Never upgrade first-field/low-resolution typing to higher resolution.
