# Human actions queue

Never put secret values in this file.

## Open

### HA-004 — Iranian histocompatibility practice must be confirmed
- **Needed by:** V1-MATCH; blocks freezing the matching spec.
- **Why:** The matching design is grounded in OPTN (US), EFI and Eurotransplant
  (EU) standards and WHO nomenclature. **No Iranian standard was consulted.**
  If Iranian practice differs on which loci are typed, how mismatches are
  counted, or how serology is reported, it outranks all of the above.
- **Decision required:** confirm with an Iranian transplant immunologist which
  loci are routinely typed, at what resolution, and how mismatch is counted
  locally. Also confirm whether the archive's lab families (Yekta, Basir,
  Gholhak, Razi) report serologic or molecular types.
- **Secret?** No.
- **Blocking now?** Blocks V1-MATCH spec freeze. Does not block MVP-HIST.

### HA-005 — Should patient names be stored in plaintext?
- **Needed by:** entity resolution (ENTITY-001); affects what identifiable data we hold.
- **Why:** The Persian pass extracted name-field cues from 8,875 reports. That
  field is the highest-PII item in the archive, is useful for linking one
  person's repeated posts, and is **irrelevant to HLA matching**. Comparing the
  two passes, Persian added only +5 laboratory markers and +360 dates — names
  were essentially its entire yield.
- **Decision required:** store the name as a **salted hash** for matching only
  (recommended — keeps the dedup value at a fraction of the exposure), or keep
  plaintext because a reviewer workflow needs to read it. `PRODUCT_CONSTITUTION`
  section 4 keeps direct identifiers hidden until mutual approval, so plaintext
  storage should be a deliberate choice.
- **Secret?** No, but the underlying data is PHI.
- **Blocking now?** Blocks ENTITY-001 design. Not blocking MVP-HIST parsing.

### HA-003 — Low-resolution threshold for mandatory human review
- **Needed by:** MEDIA-001, and every downstream OCR acceptance decision.
- **Why now:** The real archive contains **zero** thumbnail-only assets, but 77%
  of originals have a longest edge of ~520 px. The quality signal is currently
  keyed on the filename (`_thumb`) and on a missing original, so against this
  archive it never fires: low-resolution images would be classified
  `HIGH_RES_AVAILABLE` and would skip the human review the constitution requires
  before a low-resolution critical HLA value reaches Gold. Measurements in
  `docs/ingestion/ARCHIVE_CHARACTERIZATION_2026-08-31.md`.
- **Decision required:** the pixel threshold(s) separating quality bands, and
  which band forces mandatory review. A defensible starting point is: longest
  edge < 900 px => review required; 900-1280 px => review required for critical
  HLA fields; the ~0.1% above 1280 px => normal acceptance policy. **These
  numbers are a placeholder for a clinical judgement, not a recommendation the
  agent is qualified to make.**
- **Secret?** No.
- **Blocking now?** Blocks MEDIA-001 completion. Does NOT block HIST-001, which
  performs no quality classification.
- **STATUS 2026-09-02: premise corrected.** The "77% at ~520 px" figure counted
  9,581 thumbnail *copies* (`_thumb (n).jpg`) as originals (KI-009). True
  distribution of the 23,566 unique originals: 90.0% >900 px, 9.7% 561–900 px,
  0.4% ≤560 px. The decision is still needed — for the 561–900 px band and for
  the `_thumb.jpg` the export carries for every photo — but it is no longer the
  dominant accuracy risk. See `docs/ingestion/ACCURACY_REVIEW_AND_PLAN_2026-09-02.md`.

### HA-006 — py-ard / IMGT version conflict
- **Needed by:** HLA validation gate (P2 of the accuracy review), OCR-001.
- **Why now:** `HLA_VALIDATION_SPEC.md` pins IMGT/HLA 3.65, but the locked
  `py-ard` is 1.5.5 (`>=1,<2`) and `init(imgt_version="3650")` fails with
  `IndexError` (3640 too, per the research pass); `3620` loads. Verified on this
  machine 2026-09-02 (KI-011).
- **Decision required:** (a) pin IMGT 3620 with the locked library and amend the
  spec, or (b) raise the `py-ard` constraint to a 2.x release, update the OSS
  register and lockfile, and re-test 3650. The agent must not change a spec pin
  or a major dependency version silently.
- **Secret?** No.
- **Blocking now?** Blocks P2 (nomenclature validation) only; P0/P1 proceed.

### HA-001 — Local archive path (only when running real MVP-HIST ingestion)
- **Needed by:** HIST-001 real-data smoke test
- **Action:** Set `KM_TELEGRAM_EXPORT_DIR` in local `.env` to the extracted Telegram export directory.
- **Secret?** No, but machine-specific; do not commit `.env`.
- **Blocking now?** No; synthetic tests should be implemented first.
- **STATUS 2026-09-01: DONE on this machine.** Archive moved to
  `data/raw/ChatExport_2026-08-31` (gitignored) and `.env` written. Any other
  machine must repeat this; the archive is local-only and never committed.

### HA-002 — Project source-code license before public release
- **Needed by:** public/open-source release only
- **Action:** Human chooses project license. Third-party OSS licenses remain tracked independently.
- **Blocking now?** No.

## Closed
<!-- Move completed items here without inserting credentials. -->
