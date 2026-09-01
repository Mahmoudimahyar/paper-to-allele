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
