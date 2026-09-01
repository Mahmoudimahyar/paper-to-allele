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
