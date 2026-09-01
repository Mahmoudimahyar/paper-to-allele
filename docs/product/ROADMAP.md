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
