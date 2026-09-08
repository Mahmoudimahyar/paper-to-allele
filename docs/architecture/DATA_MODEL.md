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
> Superseded by MATCH-001 v2.0.0. The implementation records a pair's outcome
> as a `Bucket` plus a `BucketDecision` (`src/kidneymatch/matching/gates.py`)
> and a row as a `RankedPair` carrying a `SortKey`
> (`src/kidneymatch/matching/core.py`, `ranking.py`). The difference is
> deliberate: `status` here is one position on a linear pipeline, and a pair
> can satisfy several gate conditions at once, so every blocking reason is
> reported rather than only the furthest stage reached. See
> `docs/clinical/MATCHING_POLICY_V2.md` section 5.
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
