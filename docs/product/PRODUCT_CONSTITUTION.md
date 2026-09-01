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
