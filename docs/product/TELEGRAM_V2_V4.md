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
