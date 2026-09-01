# OCR Image Review — 10 Supplied Telegram Examples

## Summary
These 10 examples confirm that the archive often contains only **low-resolution Telegram media**. The importer should resolve any linked higher-quality asset when physically present, but MUST treat the low-resolution file as the real source when no better file exists. All ten supplied examples are thumbnail variants around 520 px tall. Two duplicate groups are exact binary duplicates, demonstrating that OCRing every thumbnail would waste work and create inconsistent outputs.

## Exact duplicates observed
- Images 1, 3 and 4: same SHA-256 (`41233f0b212f...`).
- Images 2 and 5: same SHA-256 (`1a715856808d...`).

This is a hard implementation requirement: compute SHA-256 before OCR and execute medical OCR once per unique binary asset.

## Image-specific failure patterns
### Images 1/3/4 — partially occluded Yekta report
- document is under cards/envelopes;
- upper metadata obscured;
- perspective and shadow;
- only lower HLA grid visible;
- same binary repeated three times.

**Decision:** classify as `CROPPED_OR_OCCLUDED_HLA`; look for a physically present higher-quality linked asset once; if absent, continue with the low-resolution source and mandatory review; never attempt to infer hidden identity/metadata.

### Images 2/5 — relatively clean Yekta form but still a thumbnail
- table geometry is strong;
- labels and boxes make it ideal for template-aware crop extraction;
- text pixels remain too small for reliable unrestricted full-page OCR.

**Decision:** template-align first; crop each HLA cell; upscale; OCR individual cells; best-available file is used; low-resolution source forces stricter review.

### Image 6 — photographed Yekta form
- uneven lighting;
- paper/background variation;
- table still structured;
- some loci absent/blank;
- values may be visually plausible, but thumbnail-derived critical fields require human confirmation and retain `THUMBNAIL_ONLY` provenance.

**Decision:** geometry-based locus extraction, blank cells remain UNKNOWN.

### Image 7 — non-Yekta laboratory report with Persian overlay
- overlay text/phone obscures lower document;
- image is photographed at an angle;
- clinical table and advertisement overlay are two distinct evidence layers.

**Decision:** separate `DOCUMENT_FIELD_CLAIM` from `OVERLAY_ADVERTISEMENT_CLAIM`; never let overlay text overwrite the printed report.

### Image 8 — Persian advertisement graphic, not a laboratory report
- typed HLA-like values presented in an ad;
- phone numbers and narrative are part of graphic;
- no laboratory provenance.

**Decision:** classify `ADVERTISEMENT_GRAPHIC`; values are `S0/S1 source claims`, never laboratory results.

### Image 9 — Basir/Immunogenetics form
- different template family;
- HLA-C is not shown;
- class I/class II boxes differ from Yekta;
- redacted ID area.

**Decision:** separate template; missing loci remain UNKNOWN; no assumption that all labs report same locus set.

### Image 10 — phone gallery screenshot containing a Yekta report
- gallery UI consumes most pixels;
- report itself occupies a small central area;
- status/navigation bars are non-document text;
- text-pixel height is too small for primary extraction.

**Decision:** classify `CHAT_OR_GALLERY_SCREENSHOT`; use any physically present embedded/higher-quality asset; otherwise crop the low-resolution report area and force human review.

## Local OCR benchmark observation
Tesseract 5.5 (`eng` and `fas+eng`) was run locally on four representative thumbnails. Full-page extraction was poor: HLA rows were generally not recovered reliably, one report generated malformed HLA-like fragments, and another produced essentially no useful text. This is not evidence that Tesseract is universally poor; it is evidence that **these thumbnails are insufficient input for unconstrained full-page OCR**.

## Locked consequence
The production pipeline MUST:
1. resolve the highest-quality physically available media without assuming a missing original exists;
2. deduplicate;
3. classify document/template;
4. locate cells geometrically;
5. OCR small field crops with multiple engines;
6. validate against locus-specific HLA vocabulary;
7. abstain on disagreement;
8. require human confirmation for historical Gold critical HLA.
