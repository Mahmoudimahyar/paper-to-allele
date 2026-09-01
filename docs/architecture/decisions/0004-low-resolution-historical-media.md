# ADR 0004 — Historical low-resolution media is a first-class source

**Status:** Accepted

## Decision
Use the highest-quality file physically present. If only a Telegram thumbnail/screenshot exists, mark `THUMBNAIL_ONLY` and proceed with strict extraction/review rather than assuming an unavailable original.

## Consequences
OCR evaluation is calibrated on real low-resolution inputs; critical fields require human review before Gold publication.
