# Archive characterization — ChatExport_2026-08-31

Measured 2026-09-01 against the real export now at
`data/raw/ChatExport_2026-08-31` (gitignored, local only).

**Method:** structural counts and JPEG header reads only. No message text was
read out, no image was decoded, and nothing below identifies any person. These
are aggregate figures, safe to keep in the repository.

## Scale

| | |
|---|---|
| total files | 178,660 |
| total size | 7.01 GB |
| message pages (`messages*.html`) | 183 |
| message `div`s | 183,897 |
| photo assets | 145,697 |
| documents / files | 45 (19 PDF, 1 MP4, 1 MP3, 2 APK, 7 `.npvt`) |
| contacts (vCard) | 4 |

## Message composition

| Shape | Count | Share |
|---|---|---|
| normal (`message default clearfix`) | 167,012 | 90.8% |
| **joined** (no `from_name` at all) | 13,429 | 7.3% |
| service | 3,456 | 1.9% |
| — of which date dividers (negative id) | 1,297 | |
| — of which real actions (positive id) | 2,159 | |
| **forwarded** (`forwarded body`) | 68,297 | 37.1% |
| replies (`reply_to details`) | 17,397 | 9.5% |
| media not exported | 290 | |

Two of these deserve attention during implementation:

- **Forwarding is not an edge case.** 37% of messages carry a forwarded block.
  The constitution's rule that the current poster and the forwarded author are
  different identities governs more than a third of the corpus.
- **13,429 messages carry no sender at all.** Joined messages omit `from_name`
  entirely, so sender carry-forward is load-bearing, not a nicety.

The DOM matched `TELEGRAM_HTML_EXPORT_STRUCTURE.md` exactly, including the
div-vs-anchor rule for un-exported media: 290 generic media `div`s (no link) and
290 "not included / unavailable / exceeds maximum size" descriptions.

All 247,432 timestamps carry a `UTC±HH:MM` suffix, so this is a post-2022 export.
The no-offset shape stays in the fixture as defensive coverage.

## Media resolution — this contradicts a documented assumption

| | Count | Share |
|---|---|---|
| original **and** thumbnail present | 32,687 | 22.4% |
| original only (no thumbnail) | 113,010 | 77.6% |
| **thumbnail only** | **0** | **0.0%** |

Every photo asset has its original. There is not a single thumbnail-only asset.

But the originals are themselves low resolution. Longest edge, sampled over
6,000 originals:

| percentile | px |
|---|---|
| min | 416 |
| p10 | 520 |
| p25 | 520 |
| **median** | **520** |
| p75 | 520 |
| p90 | 1280 |
| max | 2560 |

| longest edge | share |
|---|---|
| ≤ 640 px | 77.2% |
| 641–900 px | 2.1% |
| 901–1280 px | 20.6% |
| > 1280 px | 0.1% |

### What this changes

`OCR_IMAGE_REVIEW_2026-08-31.md` concluded from **10 supplied examples** that the
archive "often contains only low-resolution Telegram media … all ten around
520 px tall". The conclusion about resolution is **correct and now confirmed at
scale** — the median really is 520 px. The *mechanism* recorded alongside it is
not: those samples were not thumbnails-with-missing-originals. They were the
originals.

This matters because the quality signal is implemented on the wrong attribute.
`resolve_best_available_media` assigns `THUMBNAIL_ONLY` when the filename
contains `_thumb`, or when the linked original is absent. **Against this archive
that branch never fires.** All 145,697 assets would be classified
`HIGH_RES_AVAILABLE`, including the 77% whose longest edge is 520 px.

The consequence is a patient-safety gap, not a cosmetic one: the constitution
requires human review before a thumbnail-derived critical HLA value reaches Gold,
and `HISTORICAL_INGESTION_MVP.md` §1 ties that requirement to `THUMBNAIL_ONLY`.
As implemented, low-resolution values would skip the gate that exists to catch
them.

**Media quality must be classified by pixel dimensions, not by filename.** The
threshold is a clinical judgement, not an implementation detail — see
`HUMAN_ACTIONS.md` (`HA-003`). Until it is set, treat `MEDIA-001` as blocked on
that decision rather than guessing a number.

## Consequences for the plan

- `MEDIA-001` needs a dimension-based quality rule. Its current spec wording is
  written around a missing-original case that does not occur here.
- OCR is likely more tractable than the 10-sample review implied for the ~21% at
  901–1280 px, and no easier for the 77% at 520 px. The template-align,
  crop-cell, upscale, per-cell OCR strategy still stands.
- Exact-duplicate detection remains valuable: 32,687 assets carry both an
  original and a thumbnail of the same image, and the review found exact binary
  duplicates across messages. Hash before OCR, once per unique asset.
