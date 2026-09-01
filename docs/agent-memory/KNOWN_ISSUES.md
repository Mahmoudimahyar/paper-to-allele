# Known issues

Use one issue per heading. Remove or move to an ADR/tech-debt plan when resolved.

## KI-001 — OCR dependency pins are not frozen yet
PaddleOCR/PaddlePaddle, Surya, and OS-level Tesseract behavior must be benchmarked on the actual low-resolution archive before production pinning. This does not block message parsing/dedup.

## KI-002 — Telegram JSON stable sender IDs may not be available
HTML provides message IDs/display names/forward metadata but may not provide stable numeric actor IDs. JSON export can improve identity linkage if available; MVP-HIST must function without it.

## KI-003 — Historical records are unclaimed evidence
Historical candidates are not active platform users and must not be presented as verified/available donors merely because a phone number/report appears in the archive.

## KI-004 — Matching weights are a versioned project heuristic
The DQ/DR-prioritized V1 heuristic is documented but is not a universal clinical standard. It must remain explainable/versioned and later be reviewed/calibrated with Iranian clinical experts/outcomes.
