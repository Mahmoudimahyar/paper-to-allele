# Low-resolution historical media policy — LOCKED

## Known constraint
For the historical Telegram archive, many medical images exist only as low-resolution Telegram thumbnails/screenshots. **No engineering task may assume that a higher-resolution original exists.**

## Best-available-media resolution
For each HTML/JSON media reference:
1. If the linked `href` file physically exists, inventory it and compare quality with the displayed thumbnail.
2. If it does not exist, use the physically available thumbnail/screenshot immediately; mark `media_quality=THUMBNAIL_ONLY`.
3. Never retry indefinitely, scrape for a missing asset, synthesize detail, or claim an unavailable original.
4. Exact and perceptual dedupe happens before OCR.

## Medical extraction consequences
A low-resolution image may still produce useful evidence. For critical fields (ABO, HLA, PRA/DSA/crossmatch values):
- template geometry/cell coordinates are mandatory whenever a known form is recognized;
- multi-engine agreement may increase extraction confidence but never equals medical verification;
- candidate HLA values must pass locus-specific reference validation;
- competing plausible values => `REVIEW_REQUIRED`;
- unreadable values => `UNKNOWN`;
- a human reviewer must explicitly confirm a thumbnail-derived critical field before it can enter the historical Gold dataset;
- Gold retains `THUMBNAIL_ONLY` provenance permanently.

## Benchmark target
The OCR golden corpus must deliberately represent the archive we actually have: blurry, compressed, overlaid, cropped, rotated, photographed, and screenshot reports. A benchmark built only from clean scans is invalid for MVP-HIST.

## Error priority
Optimize for **near-zero wrong-locus false acceptance**, not generic character accuracy. Correct abstention is a success condition.
