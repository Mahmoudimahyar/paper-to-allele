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

## Resolution bands and mandatory review (HA-003, decided 2026-09-03)

Decided by the human operator, on the corrected measurement (KI-009): the
archive holds 23,566 unique originals, 90.0% above 900 px, 9.7% at 561–900 px
and 0.4% at or below 560 px. The earlier "77% at ~520 px" counted thumbnail
copies and is withdrawn.

| band | longest edge | documents | policy |
|---|---|---:|---|
| `LOW` | ≤ 560 px | 85 | **Mandatory human review** before any HLA value from it reaches Gold. No exception, no confirmer substitute. |
| `MID` | 561–900 px | 2,276 | **Provisional: mandatory review for critical HLA fields.** |
| `HIGH` | > 900 px | 21,205 | Normal acceptance policy. |

The MID rule is marked provisional because it is the one band where the cost is
real — 2,276 documents is a fortnight of somebody's reading — and where the
evidence to set it does not exist yet. The review pack (HA-008) draws a
`mid_res` stratum precisely to measure it: if MID documents are edited at the
same rate as HIGH ones, the band should be relaxed to normal acceptance; if they
are edited materially more often, the provisional rule stands and is no longer
provisional.

Until those labels exist, the conservative reading holds. A band decision that
is wrong in the permissive direction publishes bad values; wrong in the strict
direction it only costs reading time.

**This is a clinical judgement recorded by an agent, not made by one.** The
thresholds above were proposed from pixel measurements and accepted by the
operator; nothing here is derived from Iranian transplant practice, which
remains HA-004.
