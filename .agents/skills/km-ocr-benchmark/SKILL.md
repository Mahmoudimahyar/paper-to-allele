---
name: km-ocr-benchmark
description: Benchmark or modify low-resolution medical OCR/HLA extraction. Use for OCR engines, template detection, cell crops, HLA validation, consensus, or golden-corpus work.
---

# OCR/HLA benchmark rules
- Read `docs/ingestion/OCR_SPEC.md`, `LOW_RES_MEDIA_POLICY.md`, and `docs/clinical/HLA_VALIDATION_SPEC.md`.
- Benchmark the real low-resolution failure modes.
- Geometry determines locus.
- Preserve raw engine outputs and crop coordinates.
- Multi-engine agreement is supporting evidence, not enough by itself.
- Invalid/competing HLA candidates => abstain/review.
- Measure wrong-locus false acceptance separately; target zero on release golden set.
- Never make clean high-res fixtures the only benchmark.
