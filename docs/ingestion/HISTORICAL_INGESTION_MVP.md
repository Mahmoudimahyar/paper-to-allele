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
