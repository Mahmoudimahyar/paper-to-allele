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
