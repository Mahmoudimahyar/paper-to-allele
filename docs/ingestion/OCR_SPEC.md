# OCR and Document Extraction Specification

## 1. Observed image failure modes
The provided Telegram corpus includes:
- exact binary duplicate thumbnails under different names;
- small Telegram thumbnails around ~520 px tall;
- reports partially covered by cards/envelopes;
- perspective distortion;
- strong shadows and uneven lighting;
- blur and low text-pixel height;
- screenshots of a report inside a phone gallery UI;
- Persian advertisement graphics that imitate structured medical data but are not laboratory reports;
- overlaid Persian captions/phone numbers covering medical documents;
- masked/redacted national identifiers;
- multiple laboratory form families;
- cropped reports with missing metadata or loci;
- duplicated reports reposted by different Telegram actors.

A local Tesseract 5.5 test on representative supplied `_thumb` images produced poor full-page HLA extraction, including malformed tokens and empty output on some reports. Therefore unconstrained full-page OCR is **not an acceptable extraction strategy** for these thumbnails. When thumbnails are the only available source, use template/cell geometry, multi-engine consensus, strict HLA validation, abstention, and mandatory human review for critical values.

## 2. OCR philosophy
This is a constrained evidence extraction system, not general OCR.

**Rule:** Geometry determines the medical field/locus. OCR determines the characters inside that field.

The system MUST NOT full-page OCR a report, regex all `*NN` tokens, and guess their HLA loci.

**Exceptions, each measured, gated and withdrawable by its `source`** (the constitution names the same set):

1. **The grouped DRB3/4/5 row (HA-011, decided 2026-09-07).** Geometry fixes the ROW; the printed header enumerates the admissible set {DRB3, DRB4, DRB5}. A gene NAME read from a token standing on that row may set that gene's presence — never a locus outside the enumeration, never an allele's resolution. Where the header is printed but unread, the row may be placed from the page's own label pitch (`TOKEN_ANCHORED_DRBX/v1`) under the same enumeration. A bare number on the row goes to review; a null-suffixed (`N`) DRB3/4/5 allele stays `REVIEW_REQUIRED` for matching until HA-004 rules.
2. **A locus from the value's own printed prefix**, on three routes only: where the page labels nothing (`prefix-bound`), where the label was read but its cell held no box and the value stands on the label's row (`anchor-row-prefix`), and where a comparison sheet's column heading names the subject (`column-bound`). Gates in `CV_RESEARCH_2026-09-05.md` s12; HA-017, decided 2026-09-07.

## 3. Document classes
- `HLA_TYPING`
- `PRA_LUMINEX`
- `CROSSMATCH`
- `GENERAL_LABS`
- `ULTRASOUND`
- `CT_ANGIOGRAPHY`
- `CONSENT_DOCUMENT`
- `ADVERTISEMENT_GRAPHIC`
- `CHAT_SCREENSHOT`
- `EDUCATIONAL`
- `SCAM_WARNING`
- `UNRELATED`
- `UNKNOWN`

Only class-specific extractors can publish medical field proposals.

## 4. Source quality states
- `ORIGINAL_HIGH_RES`
- `ORIGINAL_MEDIUM_RES`
- `SCREENSHOT_HIGH_RES`
- `CROPPED_DOCUMENT`
- `OVERLAID_DOCUMENT`
- `LOW_RES`
- `THUMBNAIL_ONLY`
- `UNREADABLE`

## 5. Template registry
Repeated laboratory layouts MUST be implemented as versioned templates, including at minimum observed families such as Yekta, Basir/Immunogenetics, Gholhak and Razi when enough samples exist.

A template contains:
- template ID/version;
- visual anchors/logos/headings;
- reference aspect ratio;
- field bounding boxes in normalized coordinates;
- locus mapping per cell;
- optional metadata boxes;
- minimum image-quality requirements.

## 6. OCR cascade
### Stage A — preprocess
OpenCV/Pillow:
- decode safely;
- orientation detection;
- perspective correction;
- deskew;
- contrast normalization/CLAHE;
- denoise;
- upscale cell crops;
- retain original unchanged.

### Stage B — primary text OCR
Use **PaddleOCR PP-OCRv5 Arabic recognition model** for Persian/Arabic-script text and digits. Use appropriate Latin/English recognition for Latin HLA fields where benchmarked.

Decision rationale: PP-OCRv5 has an Arabic-script recognition model; Persian is in the supported Arabic-script family. The newer universal PP-OCRv6 language list must not be assumed to cover Persian unless the specific deployed model documentation confirms it.

### Stage C — independent second opinion
Tesseract 5 with `fas+eng` for Persian metadata and `eng`/restricted character set for HLA cell crops. Tesseract is a second opinion and fallback; it is not the primary HLA extractor because the thumbnail benchmark was insufficient.

### Stage D — hard-document fallback
PaddleOCR-VL for low-layout-confidence, complex tables, irregular scans or mixed Persian/English content after benchmarking. It supports Persian and document/table parsing. VLM output remains `S1_OCR_PROPOSED`.

### Stage E — benchmark alternative
Benchmark Surya against Paddle on the golden corpus. It is not a mandatory production dependency until it improves error/abstention trade-offs materially.

## 7. HLA cell recognition
For every HLA cell:
1. crop using template geometry;
2. create preprocessing variants;
3. run primary and secondary OCR;
4. normalize punctuation only;
5. constrain by expected locus vocabulary;
6. validate using pinned IPD-IMGT/HLA/py-ard;
7. compare caption claim if present;
8. decide `AUTO_PROPOSABLE` vs `REVIEW_REQUIRED`.

### Auto-proposable criteria
All must hold:
- source quality meets the benchmark for generating a proposal; `THUMBNAIL_ONLY` is allowed because it may be the only source, but a thumbnail-derived critical field can never bypass mandatory human review before Gold publication;
- template/locus confidence high;
- at least two independent recognizers agree OR one recognizer has extremely high confidence plus exact caption agreement;
- candidate is valid for expected locus under pinned HLA reference;
- no competing valid candidate within edit distance threshold;
- no conflict with other source evidence;
- image crop quality exceeds benchmark threshold.

Even an auto-proposable HLA remains `S1_OCR_PROPOSED`, not verified.

## 8. No hallucinated/fuzzy correction
Fuzzy matching may propose review choices but never silently modify medical text.

Example:
- OCR: `B*4g`
- valid same-locus candidates: `B*48`, `B*49`
- result: `REVIEW_REQUIRED`; show both suggestions and crop.

Population allele frequency MUST NOT override ambiguous image evidence. Frequency may sort human-review suggestions only.

## 9. Required extraction record
Every image-derived critical value stores:
- source document/page/media asset;
- bounding box;
- crop checksum;
- expected field/locus;
- raw OCR outputs from each engine;
- engine/model/version;
- preprocessing variant;
- confidence;
- normalized candidate;
- HLA reference version;
- user/human review action;
- final evidence state.

## 10. OCR metrics
Primary metrics:
- wrong-locus false acceptance rate (critical; target 0 on golden corpus);
- exact HLA field precision;
- exact ABO field precision;
- critical-field false acceptance;
- abstention/needs-review rate;
- template classification accuracy;
- conflict detection recall;
- processing time per unique document.

General character error rate is secondary.

## 11. Golden corpus
Before full-batch extraction:
- manually label 200 representative unique documents, expand toward 500;
- stratify by laboratory, document type and quality;
- use the highest-quality asset physically available; benchmark the real low-resolution archive, not hypothetical better inputs;
- two-person resolution for ambiguous critical HLA labels when possible;
- freeze expected JSON + bounding boxes;
- benchmark every OCR/model upgrade against same corpus.

No OCR/model upgrade may ship if it increases wrong-locus false acceptance.
