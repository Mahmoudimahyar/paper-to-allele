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
