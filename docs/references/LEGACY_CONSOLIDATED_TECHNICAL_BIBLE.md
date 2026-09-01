# KidneyMatch Iran — Executable Technical Bible v1.0
This consolidated document is generated from the authoritative modular specifications in this bundle. In conflicts, PRODUCT_CONSTITUTION.md and the specific versioned policy/config file control.

---

# KidneyMatch Iran — Executable Technical Bible v1.0

**Status:** LOCKED FOR IMPLEMENTATION OF HISTORICAL MVP AND V1 MATCHING  
**Date:** 2026-08-31  
**Primary language:** Python 3.12  
**Target geography:** Iran  
**Primary user interface sequence:** local historical tooling → Telegram bot/Mini App → public website  

This repository is the implementation contract for the KidneyMatch Iran project. It is deliberately prescriptive. A coding agent MUST NOT invent product or clinical behavior that is absent from this repository.

## Product mission
Build a free, privacy-preserving system that reconstructs kidney donor/recipient evidence from historical Telegram exports, extracts and verifies medical data, removes duplicate records without destroying provenance, performs transparent compatibility pre-screening, and later allows verified donors and recipients to register through Telegram.

## Non-negotiable principles
1. No public donor directory.
2. No price-based ranking, sorting, or promotion.
3. Compensation is stored/displayed separately from the matching engine.
4. HLA OCR is evidence extraction, not medical verification.
5. Every medical fact must be traceable to an exact source and, for image-derived facts, a bounding box/crop.
6. Missing medical data is UNKNOWN, never a match.
7. HLA values from different loci must never be mixed.
8. Historical Telegram records are HISTORICAL_UNCLAIMED until claimed and re-verified by the person.
9. Similar HLA values alone can never merge two people.
10. The medical matching engine is deterministic and versioned; no LLM makes compatibility decisions.
11. Donor-specific antibodies and crossmatch override HLA similarity when available.
12. Only one canonical person may be controlled by a normal end-user account.
13. The system is free to users and does not process payments or negotiation.
14. All critical changes are auditable.

## Read order for coding agents
1. `PRODUCT_CONSTITUTION.md`
2. `ROADMAP.md`
3. `ARCHITECTURE.md`
4. `DATA_MODEL.md`
5. `HISTORICAL_INGESTION_MVP.md`
6. `OCR_SPEC.md`
7. `HLA_VALIDATION_SPEC.md`
8. `MATCHING_POLICY_V1.md`
9. `SECURITY_TRUST_SAFETY.md`
10. `TEST_PLAN.md`
11. `AGENTS.md`
12. Feature YAML files under `specs/features/`

## Locked technology stack
- Python 3.12 latest patch
- Django 5.2 LTS
- PostgreSQL 18 latest minor
- Django templates + HTMX + Bootstrap RTL + minimal Alpine.js
- Local ETL CLI inside the same Python monorepo
- lxml/BeautifulSoup for Telegram HTML, JSON adapter for Telegram JSON
- OpenCV + Pillow for image processing
- PaddleOCR PP-OCRv5 with `lang=fa` as primary Persian OCR after benchmark
- Tesseract as independent low-cost second OCR engine, not primary HLA extractor
- PaddleOCR-VL as fallback for hard documents after benchmark
- Surya as benchmark/fallback candidate, not a mandatory production dependency until benchmarked
- py-ard pinned to IPD-IMGT/HLA 3.65 for HLA nomenclature validation
- pytest + Hypothesis + pytest-bdd + Playwright; Schemathesis when HTTP API surface exists
- Docker Compose + Caddy on a single VPS for early production
- restic encrypted backups

## Version names
- **MVP-HIST:** local historical Telegram reconstruction, OCR, dedupe, review, database
- **V1-MATCH:** recipient input → ranked top donors using reviewed database
- **V2-SYNC:** automatic daily Telegram ingestion
- **V3-BOT-INTAKE:** Telegram registration and interactive document extraction/confirmation
- **V4-BOT-MATCH:** recipient matching and mutual connection request through Telegram
- **V5-WEB:** public informational website that routes users to Telegram

---

# Product Constitution

## 1. Intended use
KidneyMatch Iran is a free kidney donor/recipient **compatibility pre-screening, evidence organization, matching, and introduction platform** for Iran. It does not replace a transplant center, HLA laboratory, donor medical evaluation, virtual crossmatch, or physical crossmatch.

## 2. Product claims
The product MAY claim that it:
- extracts and organizes data from source documents;
- identifies duplicate/related source records;
- compares reported HLA/ABO values;
- ranks candidates for **further clinical evaluation** according to a versioned pre-screening policy;
- identifies missing or conflicting information;
- facilitates a consent-based introduction after both parties complete required information.

The product MUST NOT claim that it:
- proves a donor is medically eligible;
- proves a pair is transplant-compatible without pair-specific clinical review;
- substitutes for donor-specific antibody interpretation or crossmatch;
- predicts a guaranteed transplant outcome;
- offers an official allocation decision.

## 3. Financial model
- Platform usage is free.
- Donors may state one fixed requested compensation amount after identity/profile verification in later versions.
- The platform does not process money, escrow, deposits, commissions, offers, counteroffers, or negotiation.
- Compensation is technically isolated from matching.
- Changing compensation never changes rank.

## 4. Privacy model
- Historical records remain internal and unclaimed.
- The public website contains no donor/recipient directory.
- Raw medical documents are private.
- Direct identifiers are hidden from other users until a connection is mutually approved.
- Sensitive actions require strong reauthentication in later production versions.

## 5. Evidence model
Every fact has two separate attributes:
1. **Extraction confidence** — how sure the software is that it read the characters correctly.
2. **Provenance trust** — how authoritative/authentic the source is.

These MUST NOT be conflated.

### Evidence states
- `S0_SELF_REPORTED`
- `S1_OCR_PROPOSED`
- `S2_USER_CONFIRMED`
- `S3_HUMAN_REVIEWED`
- `S4_LAB_VERIFIED`
- `S5_CENTER_VERIFIED`

Historical MVP Gold HLA requires at least `S3_HUMAN_REVIEWED`. It is still not `S4_LAB_VERIFIED` unless a laboratory actually verifies it.

## 6. Medical invariants
- ABO unknown → not treated as ABO compatible.
- Positive physical crossmatch → ordinary direct transplant ranking status `BLOCKED`.
- Known donor-specific antibody / verified unacceptable donor antigen → status `BLOCKED_OR_LAB_REVIEW_REQUIRED`.
- Missing HLA locus → `UNKNOWN`, never mismatch count zero.
- Low-resolution allele `A*02` must never be expanded to `A*02:01` without new evidence.
- DRB3, DRB4, DRB5 are distinct genes even if a laboratory form groups them.
- DQA1/DQB1 heterodimer matching can only be computed when resolution/data are adequate.
- cPRA is not a substitute for pair-specific DSA evaluation.

## 7. Human safety invariants
- A Telegram poster is not automatically the person shown in the report.
- A forwarded sender is not automatically the subject.
- A phone number is an evidence item, not proof of identity.
- A historical scam accusation is an allegation, not a confirmed fraud finding.
- A representative may assist a recipient, but a normal donor profile must ultimately be controlled/confirmed by the donor.

## 8. AI policy
AI/OCR MAY:
- classify documents;
- propose structured fields;
- propose likely duplicate clusters;
- suggest candidate HLA strings within a valid locus vocabulary;
- explain deterministic match factors.

AI/OCR MUST NOT:
- invent an HLA allele;
- infer missing high-resolution typing;
- choose a clinical value when source evidence conflicts;
- decide crossmatch outcome;
- decide medical donor eligibility;
- autonomously label a person a scammer.

---

# Locked Roadmap

## MVP-HIST — Historical reconstruction and database
**Goal:** Parse all historical Telegram exports and the best available linked images locally; reconstruct candidate evidence; deduplicate media/messages/candidate clusters; extract medically useful fields; human-review critical HLA; create Gold PostgreSQL database.

### In scope
- HTML parser and optional Telegram JSON parser.
- Message IDs, timestamps, sender display names, stable sender IDs when JSON provides them, forwarded metadata, replies, joined messages, captions, contacts, hashtags, media paths.
- Message-bundle reconstruction.
- Relevance classification.
- Best-available-media inventory, including explicit `THUMBNAIL_ONLY` status when no better asset exists.
- Exact + near-duplicate media detection.
- Document classification.
- Template registry.
- OCR cascade.
- HLA validity constraints and provenance.
- Candidate/person clustering as suggestions with human review.
- Historical Trust & Safety events.
- Reviewer UI or local review application.
- Gold database export.

### Explicitly out of scope
- Live Telegram fetching.
- Public accounts.
- User login.
- Automatic user introductions.
- Production public hosting.
- Clinician-reliable high-resolution molecular mismatch.

### Exit criteria
- Every source message imported idempotently.
- Every source media path inventoried.
- Exact duplicate images deduplicated at MediaAsset layer.
- Relevant bundle classifier evaluated on a labelled sample.
- HLA Gold fields have source bounding boxes and human confirmation.
- No known wrong-locus false acceptance in golden test corpus.
- Gold records can be queried by role, ABO, HLA loci, source and review status.

---

## V1-MATCH — Scientific pre-screening and ranking
**Goal:** Administrator enters/chooses a recipient; system returns top 10 or top 20 historical reviewed donors with transparent rank factors.

### In scope
- ABO direct-compatibility gate.
- Recipient antibody/unacceptable antigen gate when such data exist.
- HLA mismatch vectors.
- DQ/DR-prioritized evidence-informed ranking.
- Evidence-quality and uncertainty handling.
- Top-N result list with explanation.
- MatchRun versioning/reproducibility.

### Out of scope
- Automatic direct contact.
- Payments.
- Unverified eplet/PIRCHE score from low-resolution typing.
- Claims that result equals transplant clearance.

---

## V2-SYNC — Daily Telegram ingestion
**Goal:** Automatically import new authorized Telegram channel posts every day using the same ingestion engine.

### In scope
- Official Telegram Bot API for approved channels OR an approved export/sync adapter.
- Idempotent incremental ingestion.
- Edited-message handling.
- New-media dedupe.
- Review queue for new records.
- Daily/near-real-time matching refresh after Gold review.

### Out of scope
- Unapproved private-channel scraping.
- Auto-activation of unclaimed historical profiles.

---

## V3-BOT-INTAKE — Telegram donor/recipient registration
**Goal:** A user registers as donor or recipient and submits their own data/documents through Telegram/Mini App. OCR asks the user only about uncertain/critical fields.

### Locked identity rule
**One normal end-user account controls one canonical person.** This is more correct than “one test per account.” A person may need multiple legitimate documents/retests, but all must resolve to the same verified person.

### Required completion before matching access
- role selected and confirmed;
- Iranian phone/account verification strategy enabled;
- demographic core complete;
- ABO evidence supplied;
- HLA report uploaded and required fields confirmed;
- recipient antibody profile requested if available;
- consent accepted;
- no unresolved identity/document conflict.

### Bot behavior
- OCR shows proposed values.
- High-confidence non-critical metadata can be confirmed in groups.
- Every HLA allele and ABO is shown explicitly for confirmation.
- If engines disagree, bot asks the user.
- If value is syntactically invalid or locus-inconsistent, bot does not offer it as accepted; it requests a clearer image/manual choice.
- User cannot browse other people until profile completeness gate passes.

---

## V4-BOT-MATCH — Recipient matching and connection requests
**Goal:** Verified/complete recipients see top 5 or top 10 currently available anonymized donor matches.

### Visibility
Recipient sees:
- anonymous donor ID;
- ABO status;
- HLA match explanation;
- evidence/verification level;
- requested compensation when policy allows;
- availability status;
- missing clinical tests.

Recipient does not initially see:
- donor national ID;
- raw medical documents;
- home address;
- unrestricted database search.

### Connection flow
1. Recipient requests connection.
2. Donor receives anonymous request and match summary.
3. Donor accepts/declines.
4. If accepted, step-up confirmation occurs.
5. Platform introduces them using the approved contact-disclosure policy.
6. Only one active connection/referral per donor at a time in V4.

No free-form negotiation or payment inside the product.

---

## V5-WEB — Public website
**Goal:** Public information, trust, transparency and onboarding; primary call-to-action opens Telegram.

### Pages
- Home
- How it works
- Donor path
- Recipient path
- Matching methodology
- Privacy/security
- Anti-fraud policy
- FAQ
- Transparency/funding
- Contact/report abuse

No public donor list, recipient list, price list or HLA search.

---

# Architecture

## 1. Architectural style
A **modular Django monolith** is mandatory through V5 unless a measured bottleneck requires separation. No microservices in early versions.

### Modules
- `telegram_ingest`
- `source_messages`
- `media`
- `documents`
- `ocr`
- `templates`
- `evidence`
- `identity_resolution`
- `clinical`
- `matching_core`
- `matching_app`
- `trust_safety`
- `accounts` (V3+)
- `connections` (V4+)
- `audit`

`matching_core` MUST be a pure Python domain package. It MUST NOT import Django models, compensation modules, Telegram code, UI code, or LLM clients.

## 2. Data layers
### Bronze — immutable raw
- HTML/JSON Telegram exports
- original media files
- raw bytes/hash
- no canonical medical interpretation

### Silver — evidence
- parsed messages
- message bundles
- unique media assets
- duplicate clusters
- document types/templates
- OCR proposals
- structured caption claims
- evidence conflicts

### Gold — canonical reviewed
- canonical historical candidate/person clusters
- donor/recipient role state
- reviewed ABO
- reviewed HLA typing
- reviewed antibody/crossmatch data when present
- provenance references
- matching eligibility

Only Gold participates in V1 ranking.

## 3. Historical local pipeline
`km ingest` → `km bundle` → `km inventory-media` → `km dedupe` → `km classify` → `km extract-text-claims` → `km detect-documents` → `km ocr` → `km validate-hla` → `km build-review-queue` → `km resolve-entities` → `km publish-gold`.

Every command is idempotent and records a run ID, software version and input hash.

## 4. Telegram source reconstruction
Priority of context links:
1. explicit joined-message relation;
2. explicit reply relation;
3. Telegram media-group/sibling relation if available;
4. same forwarded-message block/source metadata;
5. same sender within narrow time window as weak heuristic;
6. previous/next adjacency only as a review suggestion, never automatic evidence merge.

## 5. One source message can expose four identities
Store independently:
- current Telegram actor;
- forwarded-from actor/name;
- advertised contact identity;
- medical subject/person.

Never equate them automatically.

## 6. Deployment architecture (V3+)
- Caddy terminates TLS.
- Django web process.
- PostgreSQL 18.
- PostgreSQL-backed job worker after durability spike.
- encrypted private document store.
- local OCR worker; hard VLM fallback may be separately enabled.
- encrypted restic backup target.

## 7. No external tracking
Production pages contain no advertising trackers, no third-party analytics JS, and no external CDN requirement for medical/authenticated pages.

---

# Historical Ingestion MVP Specification

## 1. Canonical inputs
Preferred order:
1. Telegram JSON export + best available media directory.
2. Telegram HTML export + best available media directory.
3. HTML + manually mapped low-resolution media when that is all the archive contains.
4. PDF/screenshot only as fallback evidence.

The importer MUST resolve the `<a href="photos/...">` asset when it exists. If that target is absent, the displayed `_thumb` asset becomes the best-available source and is explicitly marked `THUMBNAIL_ONLY`; the pipeline MUST NOT block forever waiting for a nonexistent original.

A filename containing `_thumb` is automatically marked `THUMBNAIL_ONLY` unless a better linked asset is physically present. Critical HLA extracted from `THUMBNAIL_ONLY` input requires explicit human review; low image quality is recorded as evidence uncertainty rather than treated as missing data.

## 2. Message record
Fields:
- source export ID
- chat name / stable chat ID when available
- Telegram message ID
- posted timestamp + timezone as exported
- current sender display name
- current sender stable ID when JSON supplies it
- forwarded-from display name/ID/date
- reply-to message ID
- joined flag
- raw HTML/JSON fragment reference
- plain text
- normalized Persian text
- URLs
- `tel:` phone values
- Telegram usernames/links
- hashtags
- media references

## 3. Message bundle algorithm
A Bundle is a logical candidate/ad/evidence package.

### Automatic edges
- joined messages inherit the immediately preceding non-joined message's sender/context, subject to Telegram export semantics;
- replies link to target bundle but do not merge by default;
- media group items merge when group identifier exists;
- repeated exact media do not merge bundles, only MediaAssets;
- forwarded items preserve the current poster and forwarded source separately.

### Weak expansion
If an image-only message has no caption, inspect same-current-sender messages within 120 seconds. Add as `CONTEXT_SUGGESTION`, not canonical bundle membership, unless joined/reply/media-group evidence confirms it.

## 4. Relevance anchors
A message/bundle is selected for candidate processing if any are true:
- contains an image/document;
- contains valid-looking HLA locus tokens;
- contains donor/recipient vocabulary;
- contains donor/recipient hashtags;
- contains ABO + phone/contact + transplant vocabulary;
- contains Trust & Safety/scam vocabulary;
- structurally linked to one of the above.

## 5. Message classifications
- `DONOR_AD`
- `RECIPIENT_AD`
- `CANDIDATE_AD_UNKNOWN_ROLE`
- `HLA_DOCUMENT_BUNDLE`
- `ANTIBODY_DOCUMENT_BUNDLE`
- `CROSSMATCH_DOCUMENT_BUNDLE`
- `OTHER_MEDICAL_BUNDLE`
- `ADMIN_RULE`
- `TRUST_SAFETY_REPORT`
- `EDUCATIONAL`
- `DISCUSSION`
- `UNRELATED`
- `UNKNOWN`

## 6. Text normalization
Preserve `text_raw`; create `text_normalized` using deterministic operations:
- Arabic Yeh/Kaf → Persian canonical characters;
- Persian/Arabic/Latin digits → canonical ASCII digits for parsing while preserving raw;
- whitespace and zero-width normalization;
- emoji blood-group forms normalized in structured parser only;
- phone formatting normalized to Iranian E.164 candidate form where possible.

Never rewrite medical strings in the raw source.

## 7. Claim extraction from Telegram text
Extract separate `Claim` objects for:
- role
- ABO/Rh
- age
- sex
- height/weight
- city/region
- phone/Telegram username
- HLA typed values
- requested compensation claim
- donor test-completion claims
- kidney artery/anatomy claims
- transplant center/location claims
- user-stated HLA required/excluded values
- fraud/scam allegations

Text claims are not laboratory facts.

## 8. Deduplication layers
### Media
1. exact original Telegram path
2. SHA-256
3. perceptual hash
4. geometric visual match for crops/rephotographs

### Document
- same media asset;
- same lab/report/sample ID;
- highly similar page image;
- same report metadata + HLA fingerprint → duplicate candidate only.

### Person/entity
Potential linkage signals:
- verified identity (future);
- same phone/contact;
- same Telegram stable user ID;
- same report number/lab ID;
- same name + demographic + HLA fingerprint;
- same source image across posters.

**Automatic person merge is prohibited unless there is a unique deterministic identifier with strong evidence.** HLA similarity alone can never merge people.

## 9. Do not delete duplicates
Repeated posts remain source history. They point to one media/document/candidate cluster and may reveal changes in age, phone, compensation or poster identity.

## 10. Historical activation
All reconstructed people are `HISTORICAL_UNCLAIMED`. They cannot become active user profiles until later claim + identity + consent workflow.

---

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
Use **PaddleOCR PP-OCRv5 with `lang=fa`** for Persian text. PaddleOCR documents `fa` support under PP-OCRv5; use an English/Latin recognizer for HLA cell crops when benchmarked to outperform the Persian recognizer.

Decision rationale: PaddleOCR explicitly lists `fa` (Persian) under PP-OCRv5 language support. Its current PP-OCRv6 language table does not list `fa`, so the initial implementation pins PP-OCRv5 for Persian rather than choosing v6 merely because it is newer.

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

---

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

---

# HLA Validation and Nomenclature Specification

## 1. Reference authority
Pin **IPD-IMGT/HLA release 3.65 (2026-07)** for the initial implementation. Store the release number with every normalization/extraction run.

Use `py-ard` to validate/normalize historical HLA nomenclature against the pinned database. The application MUST NOT maintain a handwritten static list of all possible alleles.

## 2. Supported loci
Core:
- HLA-A
- HLA-B
- HLA-C
- HLA-DRB1
- HLA-DRB3
- HLA-DRB4
- HLA-DRB5
- HLA-DQA1
- HLA-DQB1
- HLA-DPA1
- HLA-DPB1

A raw invalid label such as `DQR1` is preserved as a source claim but not accepted as a canonical locus.

## 3. Dynamic valid vocabulary
At build/reference-import time generate:
- exact valid allele set per locus;
- valid first-field groups per locus;
- valid two-field alleles per locus;
- serology mappings when required;
- historical nomenclature mappings supported by py-ard.

For a low-resolution printed result `A*02`, accept it as low-resolution if `A*02` is a valid first-field family; do not infer a second field.

## 4. Normalization rules
Preserve three values:
- `raw_value`
- `normalized_notation`
- `resolution`

Examples:
- `A 02` → normalized `A*02`, resolution `FIRST_FIELD` when locus geometry confirms A.
- `A*02:01` remains two-field.
- `B35` may map to a serology/legacy claim only when the source type indicates antigen/serology; do not assume allele notation.

## 5. Ambiguity
If multiple valid HLA strings fit the OCR crop, status is `AMBIGUOUS_REVIEW_REQUIRED`.

Do not resolve ambiguity by:
- most common allele;
- closest donor match;
- what improves recipient ranking;
- LLM preference.

## 6. DQ representation
When only DQB1 is available, store DQB1 only. Do not claim complete HLA-DQ heterodimer typing.

When high-resolution DQA1 + DQB1 are available, construct DQ alpha/beta heterodimer candidates according to validated phasing rules. If phase is unknown, preserve ambiguity and do not pretend a single heterodimer configuration is known.

## 7. DRB3/4/5
Store DRB3, DRB4, DRB5 as separate loci/features. A form row labeled `DRB3/4/5` is a presentation grouping, not a single gene.

## 8. Reference versioning
Every MatchRun stores:
- HLA reference database version;
- matching policy version;
- normalization library version;
- input typing resolution.

Re-running with a future IPD release creates a new MatchRun; historical output remains reproducible.

---

# Data Model

## 1. Source domain
### `SourceExport`
- id UUID
- format HTML/JSON
- source path/hash
- chat title
- imported_at
- importer_version

### `TelegramActor`
- id UUID
- stable_telegram_user_id nullable
- current_display_name nullable
- first_seen / last_seen
- historical_unverified boolean

### `TelegramActorName`
- actor_id
- display_name
- observed_at/message_id

### `TelegramMessage`
- id UUID
- source_export_id
- telegram_message_id
- actor_id nullable
- posted_at
- forwarded_actor_id nullable
- forwarded_name_raw nullable
- forwarded_original_at nullable
- reply_to_telegram_message_id nullable
- joined boolean
- raw_text
- normalized_text
- raw_fragment_locator

### `MessageBundle`
- id UUID
- bundle_type
- bundle_confidence
- review_status

### `BundleMessage`
- bundle_id
- message_id
- relation (`PRIMARY`, `JOINED`, `REPLY_CONTEXT`, `MEDIA_SIBLING`, `WEAK_CONTEXT`)

## 2. Media/document domain
### `MediaAsset`
- id UUID
- telegram_original_path
- thumbnail_path(s)
- sha256
- perceptual_hash
- width/height
- source_quality
- original_found boolean
- mime

### `MessageMedia`
- message_id
- media_asset_id
- position

### `Document`
- id UUID
- media_asset_id
- type
- template_id/version
- quality_state
- page count
- classification confidence
- reviewer status

### `ExtractionRun`
- id UUID
- document_id
- engine/model/version
- preprocessing version
- started/finished
- output JSON checksum

### `FieldClaim`
- id UUID
- subject_candidate_id nullable
- document_id/message_id
- source_kind (`CAPTION`, `OCR`, `USER`, `HUMAN`, `LAB`, `CENTER`)
- field_type
- locus nullable
- raw_value
- normalized_value nullable
- value_json
- bbox nullable
- extraction_confidence nullable
- provenance_trust
- evidence_state
- conflict_group_id nullable

## 3. Person/candidate domain
### `PersonCandidate`
- id UUID
- status (`HISTORICAL_UNCLAIMED`, `CLAIMED`, `ACTIVE`, `WITHDRAWN`, `MERGED`)
- canonical_role (`DONOR`, `RECIPIENT`, `UNKNOWN`)
- canonical profile fields only after resolution

### `CandidateSourceLink`
Links candidate to bundles/messages/documents with relation confidence.

### `ContactClaim`
- candidate_id
- phone/email/telegram username
- source
- normalized value
- verification state

### `EntityResolutionLink`
- candidate_a/candidate_b
- relation (`POSSIBLE_SAME_PERSON`, `CONFIRMED_SAME_PERSON`, `NOT_SAME_PERSON`)
- evidence reasons
- reviewer

## 4. Clinical domain
### `ABOResult`
- candidate_id
- ABO A/B/AB/O/UNKNOWN
- Rh +/−/UNKNOWN
- source/evidence state
- specimen/report metadata

### `HLATypingReport`
- candidate_id
- document_id
- method
- resolution
- lab
- sample/report dates
- reference/normalization status

### `HLAResult`
- report_id
- locus
- allele_index 1/2 nullable
- raw_value
- normalized_value
- resolution
- evidence state

### `AntibodyProfile`
- recipient_id
- specimen_date
- PRA Class I/II nullable
- cPRA nullable
- assay/method
- status/freshness

### `AntibodySpecificity`
- profile_id
- specificity/locus
- unacceptable boolean/unknown
- MFI nullable
- evidence state

### `CrossmatchResult`
- recipient_id
- donor_id
- type (`VIRTUAL`, `FLOW_T`, `FLOW_B`, `CDC`)
- result
- specimen dates
- lab interpretation
- evidence state

### `DonorHealthEvidence`
Structured claims/statuses for kidney function, imaging, anatomy, etc. Historical caption claims do not equal medical clearance.

## 5. Matching domain
### `MatchRun`
- id UUID
- recipient snapshot hash
- donor pool snapshot hash
- policy version
- HLA reference version
- code commit/version
- created_at

### `MatchResult`
- match_run_id
- donor_id
- rank
- status
- weighted_penalty nullable
- mismatch vector JSON
- blockers JSON
- unknowns JSON
- explanation JSON

## 6. Trust & Safety
### `TrustSafetyEvent`
- type
- reporter/source message
- reported identifiers
- allegation/finding status
- review status
- evidence references

Historical accusation MUST default to `ALLEGATION_UNVERIFIED`.

## 7. V3+ account model
### `Account`
One account → one canonical `PersonProfile` for normal users.

A person may upload multiple documents/retests; this is not the same as controlling multiple people.

### `PersonProfile`
- account_id unique
- role
- completeness
- active HLA identity
- identity assurance

### `ProfileDocument`
Multiple documents allowed only for the same person; identity conflicts pause profile.

### `ConnectionRequest` V4
- recipient
- donor
- match_run/result
- recipient accepted
- donor accepted
- disclosure status
- active/expired/declined

---

# Matching Policy V1 — `IR_KIDNEY_SCREEN_1.0`

## 1. Important distinction
There is **no universally accepted clinical standard that assigns a fixed percentage weight to each HLA locus** for living-donor kidney selection. Current clinical safety still depends primarily on ABO compatibility, recipient anti-HLA antibody profile/unacceptable antigens, donor HLA, virtual/physical crossmatch and donor medical suitability.

Recent literature strengthens the importance of Class II molecular mismatch, especially HLA-DQ and HLA-DR, but the literature itself states that evidence is not yet sufficient to turn one DQ mismatch metric into a universal allocation rule. Therefore V1 uses a transparent **pre-screening policy** rather than pretending an arbitrary weighted sum is a medical standard.

## 2. Input requirement
A donor may enter V1 ranking only if:
- canonical role is donor;
- record is Gold/human-reviewed for required HLA fields;
- ABO is known or explicitly marked unknown;
- no Trust & Safety quarantine blocks use;
- donor is not withdrawn/inactive.

Recipient input contains:
- ABO;
- reviewed HLA typing;
- antibody profile/unacceptable antigens when available;
- crossmatch results when available.

## 3. Hard clinical gates
### Gate A — ABO
Use ABO letter compatibility for kidney screening. Rh is stored but not used as the kidney ABO gate.

Direct ABO-compatible donor letters:
- recipient O ← O
- recipient A ← A or O
- recipient B ← B or O
- recipient AB ← A, B, AB or O

Unknown ABO → `INSUFFICIENT_ABO`, never compatible.

### Gate B — pair-specific antibody conflict
If a reviewed recipient unacceptable antigen/DSA specificity clearly targets a reviewed donor HLA value, result = `BLOCKED_DSA_OR_LAB_REVIEW` and it cannot outrank a pair without such a conflict.

If antibody information is missing, status = `ANTIBODY_UNKNOWN`. Missing antibody data is not interpreted as negative.

### Gate C — physical crossmatch
Positive verified physical crossmatch → `BLOCKED_POSITIVE_CROSSMATCH`.
Negative physical crossmatch outranks pairs without a physical crossmatch, but only when data are current/valid.

## 4. Conventional mismatch calculation
Count donor antigens/alleles not represented in recipient at each available locus while respecting typing resolution and equivalence policy.

Return:
- A mismatch: 0/1/2/UNKNOWN
- B mismatch: 0/1/2/UNKNOWN
- C mismatch: 0/1/2/UNKNOWN
- DRB1 mismatch: 0/1/2/UNKNOWN
- DQB1 mismatch: 0/1/2/UNKNOWN
- DRB3/4/5 compatibility flags
- DQA1/DPA1/DPB1 data availability

Never convert UNKNOWN to 0.

## 5. Primary ranking — lexicographic, not a fake percentage
Sort eligible donor pairs by the following ordered tuple, lower is better:
1. verified immunologic blocker status: clear < antibody unknown < indeterminate/conflict < blocked;
2. verified physical/virtual crossmatch stage: negative/acceptable < not performed < indeterminate < positive;
3. **HLA-DQ compatibility**: high-resolution DQαβ mismatch if valid; otherwise DQB1 mismatch;
4. HLA-DRB1 mismatch;
5. combined Class II mismatch burden;
6. HLA-B mismatch;
7. HLA-A mismatch;
8. HLA-C mismatch;
9. total conventional mismatch burden;
10. evidence-quality penalty;
11. number of unknown required fields;
12. record freshness/availability;
13. deterministic random/stable ID tie breaker — never price.

This makes DQ the highest HLA ranking priority without claiming an unsupported universal percentage weight.

## 6. Secondary weighted penalty — internal tie-breaker only
To satisfy deterministic fine ordering when the tuple is otherwise tied, compute `screening_mismatch_penalty_v1`:
- DQB1 mismatch: 5 points each
- DRB1 mismatch: 4 points each
- B mismatch: 2 points each
- A mismatch: 1 point each
- C mismatch: 1 point each
- confirmed DRB3/4/5 mismatch/presence conflict relevant to available data: 1 point

If high-resolution DQA1/DQB1 heterodimer mismatch is valid, replace DQB1 penalty with DQαβ penalty of 6 per mismatched expressed heterodimer class defined by the advanced policy; do not double-count DQB1.

**These numeric coefficients are engineering policy coefficients, not a published universal medical standard.** They MUST be stored in YAML, versioned, displayed only in admin/debug explanation, and recalibrated/validated on Iranian outcome data before any clinician-reliability claim.

No user-facing “92% compatibility” is shown.

## 7. Why DQ/DR are prioritized
Recent multicenter and molecular mismatch literature associates HLA-DQ/DR mismatching, especially DQ alpha/beta and DQ eplet burden, with dnDSA, rejection and graft outcomes. Class II eplet/PIRCHE molecular mismatches are associated with AMR in large multicenter cohorts. This supports Class II priority as a pre-screening/tie-breaking direction.

However, current transplant policies/guidelines still use conventional HLA and crossmatch/DSA frameworks; molecular matching is not a universal replacement. Therefore the algorithm deliberately separates standard clinical gates from experimental/advanced risk refinement.

## 8. Advanced matching plugin (future, only with high-resolution typing)
When actual high-resolution typing exists:
- compute DQA1/DQB1 heterodimer mismatch;
- evaluate validated eplet mismatch method only through a licensed/validated implementation;
- optionally integrate PIRCHE-II as external/licensed plugin;
- record algorithm and reference versions;
- never derive clinical high-resolution results by imputing low-resolution Telegram typing for production ranking.

Imputation may be used only in a research/sensitivity namespace and MUST be clearly excluded from clinical output.

## 9. HLA-DP
DPA1/DPB1 are required for complete antibody/vXM interpretation when relevant. In V1 low-resolution long-term ranking they are not assigned a routine baseline penalty because the project lacks validated local weighting; a known recipient DP antibody against donor DP is handled by the DSA/unacceptable-antigen gate.

## 10. Recipient preferences
Historical Telegram constraints such as donor sex, age limit, single artery, or city are stored as `USER_PREFERENCE_CLAIM` unless clinically verified. They MUST NOT alter immunologic match score.

V1 UI may optionally filter/annotate preferences after biological ranking, but the biological rank remains visible and unchanged.

## 11. Compensation isolation
Matching core has no permission/import path to compensation records. Compensation never appears in match input or rank tuple.

## 12. Output
Each ranked donor returns:
- rank;
- match stage;
- ABO route;
- mismatch vector;
- DQ/DR rationale;
- antibody/crossmatch status;
- evidence quality;
- unknown/missing data;
- blockers;
- next clinical action;
- policy/reference versions.

---

# Telegram V2-V4 Specification

## V2 — Daily ingestion
- Use a separate authorized collector bot/token for whitelisted channels.
- New/edited posts are ingested idempotently.
- Store Telegram update/message IDs and edits as versions.
- Download original media where Bot API permissions support it.
- New records enter Silver/review, not Gold automatically unless low-risk non-critical metadata only.
- HLA medical facts always follow OCR/review evidence policy.

## V3 — User intake
### Account rule
One normal Telegram/web account maps to one canonical person profile.

### Role
User selects donor or recipient. Changing role after medical documents exist triggers review.

### Required donor intake
- phone/contact verification
- name/identity fields required by policy
- age/date of birth
- sex
- city
- ABO report/value
- HLA report
- donor test completion checklist
- availability
- compensation request when enabled
- consent

### Required recipient intake
- same identity core
- ABO
- HLA report
- PRA/cPRA/antibody/Luminex documents when available
- prior transplant/sensitization history prompts
- transplant center/location when available
- consent

### OCR conversation
For every critical field:
`I read HLA-B as B*49. Is this correct? [Yes] [No] [Upload clearer photo]`

If uncertain:
`I cannot safely distinguish B*48 from B*49. Please choose after checking the highlighted crop or upload a clearer image.`

The bot MUST NOT ask users to type a guessed value if a clearer report can be obtained; manual correction is allowed but remains `S2_USER_CONFIRMED`, not laboratory-verified.

### Profile completeness gate
No match browsing or connection request until required data are complete and unresolved conflicts are cleared.

## V4 — Matching
Only recipients see donor match lists by default.

### Top list
Default top 5, expandable to top 10. No full donor database search.

### Donor card
- anonymous donor ID
- ABO
- match stage and HLA mismatch explanation
- evidence state
- availability
- fixed requested compensation (when enabled)
- `Request connection`

### Connection
- recipient submits request;
- donor receives anonymous match summary;
- donor accepts/declines;
- no negotiation/payment endpoint;
- after mutual acceptance, disclose only the approved contact fields;
- one active connection per donor at a time initially;
- every disclosure is audited.

---

# Security, Anti-Broker and Anti-Fraud Specification

## 1. Anti-broker constitution
- no public donor directory;
- no unauthenticated donor data;
- no price sorting/filtering;
- no unrestricted donor-recipient chat in early versions;
- one canonical person per normal account;
- donor must personally confirm donor role, availability and compensation in V3+;
- historical imports are unclaimed;
- no direct bulk export for staff;
- rate limit match views and connection requests;
- one active connection per donor initially;
- all sensitive access audited.

## 2. Fraud graph
Store graph-friendly links between:
- Telegram actors/stable IDs;
- phones/usernames;
- accounts;
- candidate/person clusters;
- media SHA256/perceptual hashes;
- report IDs/lab IDs;
- connection requests;
- Trust & Safety events.

PostgreSQL is sufficient initially; no graph DB required.

## 3. Historical allegations
Messages that accuse someone of fraud create `TrustSafetyEvent(status=ALLEGATION_UNVERIFIED)`. They do not create `person.is_scammer`.

Multiple independent evidence sources may escalate a review priority but require human determination.

## 4. High-value signals
- same verified identity controlling multiple donor profiles;
- same report used under different claimed identities;
- multiple unrelated donors controlled from same account/contact;
- payment/deposit/bank/crypto request through platform channel;
- known prohibited broker identifiers;
- repeated profile/compensation manipulation around connection attempts.

## 5. Staff least privilege
- document reviewer: source docs + extraction, limited identity;
- clinical reviewer: medical facts, compensation hidden by default;
- trust & safety: relevant identifiers/events, no unnecessary clinical detail;
- support: account state, no raw HLA docs;
- infrastructure admin: infrastructure, no routine clinical access.

## 6. Audit
Audit:
- document view/download;
- identity view;
- field correction;
- Gold publication;
- match run;
- compensation view/change;
- connection request;
- disclosure;
- suspension/quarantine;
- break-glass access.

Do not put raw HLA, national ID, full phone, passwords/tokens or report text into ordinary security logs.

## 7. Upload safety V3+
Allow only JPEG/PNG/WebP/PDF initially. Validate magic/MIME, randomize storage names, enforce size/page limits, scan/sanitize, process in isolated worker and never serve raw upload from web root.

---

# Open-Source Dependency Policy and Initial Register

## Policy
Reuse mature open-source software for generic infrastructure. Write custom code only for domain-specific behavior or where a dependency fails quality/security/license review.

Every dependency requires:
- exact purpose;
- license;
- pinned version/lock hash;
- maintenance/security review;
- data/network access review;
- replacement plan.

## Initial decisions
| Area | Library/tool | Decision |
|---|---|---|
| Web | Django 5.2 LTS | ADOPT |
| DB | PostgreSQL 18 | ADOPT |
| Dynamic HTML | HTMX | ADOPT |
| Styling | Bootstrap RTL | ADOPT |
| Small JS | Alpine.js | NARROW USE |
| Telegram HTML parse | lxml / BeautifulSoup | ADOPT |
| Batch ETL | Polars + Parquet | ADOPT after dependency install/spike |
| Images | Pillow + OpenCV | ADOPT |
| Primary Persian OCR | PaddleOCR PP-OCRv5 (`lang=fa`) | ADOPT after golden benchmark |
| Second OCR | Tesseract 5 (`fas`, `eng`) | ADOPT as second opinion |
| VLM fallback | PaddleOCR-VL | ADOPT after resource/accuracy benchmark |
| OCR alternative | Surya | BENCHMARK, not mandatory |
| HLA nomenclature | py-ard | ADOPT with pinned IPD release and license review |
| Fuzzy text | RapidFuzz | ADOPT |
| Perceptual hashing | imagehash or `perception` | SPIKE then pin one |
| Testing | pytest, Hypothesis, pytest-bdd | ADOPT |
| Browser E2E | Playwright | ADOPT V3+ |
| HTTP schema tests | Schemathesis | ADOPT when API exists |
| TLS | Caddy | ADOPT |
| Backups | restic | ADOPT |

## Explicitly not used in early versions
- React/Vue SPA framework
- Kubernetes
- microservices
- Kafka
- Elasticsearch
- Redis/Celery unless PostgreSQL-backed jobs fail durability needs
- general LLM as matching authority
- cloud OCR as default

---

# TDD and Verification Plan

## 1. Coding philosophy
Tests are executable product specifications. Critical rules are written as failing tests before implementation.

## 2. Test layers
- unit
- property-based
- parser golden tests
- OCR golden tests
- DB constraint tests
- integration
- acceptance/Gherkin
- permissions/security
- end-to-end
- backup/restore
- mutation testing for matching/authorization/consent

## 3. Historical parser invariants
- same export imported twice creates zero duplicate messages;
- joined message inherits correct structural context;
- forwarded current sender and forwarded sender remain distinct;
- reply target links without accidental bundle merge;
- same original media path references one MediaAsset;
- same SHA256 references one binary asset;
- repeated source messages are preserved.

## 4. OCR invariants
- thumbnail cannot auto-publish HLA to Gold;
- HLA-B cell cannot populate DQB1;
- DQB1 cell cannot populate HLA-B;
- invalid HLA nomenclature requires review;
- low-resolution value is never upgraded to high-resolution;
- OCR disagreement requires review;
- caption/document conflict requires review;
- DRB3/4/5 stored separately;
- every Gold HLA field has source/crop provenance;
- model upgrade may not worsen wrong-locus false acceptance.

## 5. Dedup/entity invariants
- same HLA different people never auto-merge;
- same phone alone never hard-merges people;
- exact report ID + same lab may create strong duplicate candidate but still preserves sources;
- fraud allegation does not automatically mark confirmed fraud.

## 6. Matching invariants
- ABO unknown never passes compatible;
- positive physical crossmatch blocks ordinary direct ranking;
- known DSA/unacceptable antigen against donor cannot be ignored by HLA score;
- missing locus is UNKNOWN, not zero mismatch;
- changing compensation does not alter rank;
- matching core cannot import/query compensation;
- DQ priority outranks B/A/C when otherwise clinically comparable according to policy;
- same inputs + same policy/reference versions → identical rank;
- high-res DQ algorithm never runs on low-res-only typing.

## 7. V3/V4 security invariants
- one normal account cannot create two active people;
- multiple documents allowed only for same person; identity conflict pauses profile;
- recipient cannot browse matches before completeness gate;
- donor cannot see full recipient list;
- connection requires mutual action;
- all disclosure is audited;
- no payment/counteroffer endpoint exists.

## 8. Golden OCR acceptance targets
Before processing full corpus:
- 200 manually labelled unique documents minimum;
- 100% correct locus association after human-review workflow;
- automated wrong-locus false acceptance: 0 on golden set;
- critical-field auto-proposal precision target >= 99.5%; if not met, raise abstention threshold;
- all remaining uncertainty routed to review.

The system optimizes for precision and safe abstention, not maximum automation.

## 9. CI commands
- `just check`: formatting/lint/types/fast unit tests
- `just verify`: full unit/property/parser/integration/security suite
- `just verify-ocr`: golden OCR benchmark
- `just verify-match`: matching corpus + property tests + mutation tests
- `just release-verify`: all above + backup restore + dependency/security scan

---

# Coding Agent Contract

1. Read `PRODUCT_CONSTITUTION.md` before coding.
2. Implement only the active roadmap version and READY feature specs.
3. Do not invent requirements. If two documents conflict, stop and report the contradiction.
4. Write/update failing tests before implementation for every domain rule.
5. Never weaken a test to make implementation pass unless the specification changed through an ADR.
6. Never place real patient/donor PII/medical images in source control, prompts, fixtures, screenshots, traces or logs.
7. Historical raw inputs remain immutable.
8. Every derived medical fact keeps provenance.
9. OCR is proposal-only; never mark OCR as lab verified.
10. Geometry defines HLA locus. Never infer locus from OCR token alone.
11. Never infer high-resolution HLA from low-resolution data in production.
12. Matching core must remain deterministic and must not access compensation.
13. Missing values are UNKNOWN.
14. No LLM may make a compatibility or fraud finding.
15. Run feature-specific verification plus `just verify` before completion.
16. Update traceability mapping and ADRs for architecture/policy changes.
17. Do not add an OSS dependency without recording license/purpose/version/replacement plan.
18. Never use a `_thumb` file as preferred medical source when its original image is available.
19. If OCR output is ambiguous, choose abstention/review, never the most convenient value.
20. Report completion only when tests, migrations, docs and rollback path are complete.

---

# Research References — frozen for Technical Bible v1.0

## OCR / nomenclature
- PaddleOCR documentation: PP-OCRv5 Arabic recognition model; PaddleOCR-VL multilingual document parsing including Persian.
- Tesseract tessdata: Persian (`fas`) trained data.
- IPD-IMGT/HLA Database: release 3.65, July 2026.
- NMDP Bioinformatics `py-ard`: HLA nomenclature validation/reduction with versioned IPD/IMGT-HLA data.

## Kidney matching / immunology
- Battle et al. BSHI/BTS guideline on detection of alloantibodies in solid organ transplantation, 2023.
- BSHI/BTS guidance on crossmatching before deceased donor kidney transplantation, 2022.
- The Impact of HLA-DQ alpha/beta Heterodimer Mismatch on Living Donor Kidney Allograft Outcomes; 3916 pairs, 11 US centers.
- Chou-Wu et al. De Novo donor-specific anti-HLA antibody risk stratification using B- and T-cell molecular mismatch; 843 kidney recipients; 2025.
- Nature Communications 2025 multicenter study of 5159 recipients: Class II eplet mismatch and DQB1/DRB1-derived PIRCHE-II associations with AMR.
- Recent eplet mismatch review describing strong HLA-DQ associations and current implementation limitations.
- OPTN kidney policy/current policy materials retain conventional HLA-ABDR concepts; molecular/eplet matching is not yet a universal replacement.

**Interpretation used by this project:** ABO + antibodies/DSA + crossmatch remain hard safety gates. DQ/DR molecular/conventional mismatch informs pre-screening ranking and future risk refinement but does not overrule pair-specific antibodies or crossmatch.
