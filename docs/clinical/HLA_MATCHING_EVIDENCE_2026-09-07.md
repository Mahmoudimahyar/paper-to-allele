# HLA matching evidence review — locus ranking and per-mismatch weights

**Date:** 2026-09-07 · **Status:** EVIDENCE REVIEW, feeds a policy v2 proposal ·
**Decides nothing by itself.** Any change to the ranking or the coefficients is a
policy version change (`MATCHING_POLICY_V1.md` §6, MATCH-001 invariant "DQ/DR
priority is versioned policy") and needs HA-004 (Iranian histocompatibility
practice) before the V1-MATCH spec is frozen.

Sources: PubMed (metadata and PMC full text, 2026-09-07) and the Consensus
index. Every clinical claim below carries its DOI or a Consensus link. Where a
number comes from a conference abstract rather than a paper, it says so.

---

## 0. The answer in one page

**Locus ranking, for a living-donor pre-screen on low-resolution typing:**

| Rank | Locus | Why | Evidence strength |
|---|---|---|---|
| 1 | **HLA-DRB1 (DR)** | The only single locus whose *antigen-level* mismatch still predicts graft failure in modern deceased- and living-donor registries; the locus every allocation scheme weights first; the paired-kidney ESP study shows the benefit is causal-grade. | Strong |
| 2 | **HLA-DQB1 (DQ)** | The most immunogenic locus: most de novo donor-specific antibodies (dnDSA), antibody-mediated rejection (AMR) and re-listing sensitization are anti-DQ. Independent of DR in living donors. But low-resolution DQ typing misclassifies the mismatch in ~43% of pairs, so at one-field resolution it is less *reliable* than DR. | Strong for dnDSA/AMR/sensitization; moderate for graft survival |
| 3 | **HLA-B** | Second class I locus in every scheme (UK levels, Brazil points); per-mismatch hazard for rejection above A in the registry models; in one paediatric living-donor model B mismatch outweighed DR. | Moderate |
| 4 | **HLA-A** | Weakest of the classic three; small rejection-odds effect, no independent graft-survival effect in the modern-era models; two schemes ignore it entirely. | Weak–moderate |
| 5 | **HLA-C** | Antigen-level mismatch hurts only in *presensitized* recipients (CTS, n=2,260); no effect in the unsensitized; C mismatches ride on B (85% of B-mismatched pairs are C-mismatched). Counts only when typed (20% of profiles). | Weak; via the antibody gate |
| — | **DRB3/4/5** | No antigen-level outcome literature found; they enter molecular scores as part of class II. Keep the presence-conflict tie-breaker; matching use stays REVIEW until HA-011(b). | None at antigen level |
| — | **DQA1** | Matters as the α-chain of the DQαβ heterodimer, which needs two-field typing (776 profiles carry it). No baseline weight; heterodimer plugin only. | High-resolution only |
| — | **DPB1/DPA1** | Antibody-level danger (isolated DP-DSA ≈ DR-DSA), allele-level mismatch not predictive; 34 profiles carry it. No baseline weight; DSA gate only. Unchanged from V1 §9. | DSA-level only |

**One versus two mismatches.** The registries agree that risk rises with every
additional mismatch (roughly linear in the total count: +13% per first
mismatch, +64% at six in deceased donors; +44% and 2× in living donors). For DR
the curve is concave: the *first* DR mismatch costs most of the 10-year
survival penalty (−13%) and the second adds less (−17% total). For DQ the
second mismatch still adds a lot of rejection risk (aHR 1.68 for two DQαβ
mismatches even after controlling for DR). Every allocation scheme that grades
DR gives a distinct premium to *zero* DR mismatches. The proposal therefore
prices each mismatch linearly and adds a **zero-mismatch bonus at DR and DQ**,
which is how a "both alleles match" premium is expressed without inventing a
new curve. Second-mismatch cost relative to the first under the proposal: DR
0.67, DQ 0.80, B/A/C 1.0.

**What the archive can support.** One-field typing (97% of values), both
alleles present on every typed locus, ABO on 46% of profiles, no antibody, PRA
or crossmatch data at all. Every molecular method (eplets, PIRCHE-II, EMS-3D,
HLA-EMMA, Snow) needs two-field typing and the constitution forbids imputing
it for clinical output. So V2 is an **antigen-level pre-screen**, and every
pair is `ANTIBODY_UNKNOWN` until a lab result exists.

---

## 1. What the question was, and the guard-rails

The operator asked for a matching system on "the latest scientific evidence":
which loci matter more, whether both alleles must match at some loci, and how
much the second mismatch should weigh, with HLA-C and HLA-DRB1 as examples.

Guard-rails from the constitution and MATCH-001 that this review respects:

- ABO, DSA and crossmatch gates precede any HLA heuristic; missing values are
  `UNKNOWN`, never zero mismatch.
- No high-resolution inference from low-resolution typing; imputation only in
  a research namespace, excluded from clinical output (`MATCHING_POLICY_V1` §8).
- No compatibility percentage; a lexicographic tuple with a versioned,
  admin-only numeric tie-breaker.
- Matching never reads compensation.
- HA-004: an Iranian transplant immunologist must confirm which loci are typed,
  at what resolution, and how mismatch is counted locally, before the spec
  freezes. Nothing here overrides that.

---

## 2. The archive, measured (counts only, Gold DB of 2026-09-07)

| | Profiles |
|---|---|
| Gold profiles (unique photographs) | 19,200 |
| …with at least one HLA value | 14,864 |
| HLA-A / HLA-B / HLA-DRB1 typed | 12,131 / 11,602 / 12,258 |
| HLA-DQB1 typed | 12,234 |
| HLA-C typed | 3,794 (20%) |
| HLA-DQA1 typed | 776 |
| HLA-DPB1 / DPA1 typed | 34 / 26 |
| DRB3 / DRB4 / DRB5 presence rows | 10,062 / 9,583 / 9,304 |
| A, B and DRB1 all present | 9,817 (DONOR 5,606 · RECIPIENT 3,103 · UNKNOWN 1,108) |
| A, B, C, DRB1 and DQB1 all present | 2,678 |
| ABO known | 8,792 (A 3,242 · O 2,688 · B 2,187 · AB 675) |
| Antibody / PRA / crossmatch fields | none |

Typing resolution of the stored values: one-field (`LOCUS*NN`) on 97% of A, B,
C, DRB1 and DQB1 values; two-field on well under 1%; a few hundred bare numbers
per locus. Every typed locus carries its second allele. Evidence tiers: DRB1
and DQB1 are mostly tier A (7,609 and 7,549 rows); A and B are tier B (no
labelled cells yet); C is 62% tier A.

Consequences for the design:

1. The five-locus (A, B, C, DRB1, DQB1) antigen-level mismatch vector is
   computable on 2,678 profiles; the four-locus vector (without C) on ~9,800.
   C is `UNKNOWN` on four profiles in five and must sort as unknown, not as 0.
2. DQαβ heterodimer mismatch (V1 §5 step 3, §6) is not computable on this
   archive; V1 already falls back to DQB1. The low-resolution caveat on DQ
   (§4.2 below) applies to almost every pair.
3. Every pair is `ANTIBODY_UNKNOWN` (V1 Gate B). The literature on HLA-C and
   on repeat mismatches says sensitization is what turns a minor locus into a
   major one, so the pre-screen must show that status loudly.

---

## 3. How the allocation systems weight HLA today

The systems are the "best-performing algorithms" in the sense that they are
the ones validated on hundreds of thousands of transplants and still in force.
None of them weights DQ or C at antigen level; all of them put DR first.

| System | HLA component | Source |
|---|---|---|
| **OPTN / UNOS KAS (US, 2014→)** | Priority class for 0-ABDR mismatch; points for 0-DR and for 1-DR mismatch; A and B otherwise unweighted. HLA was deliberately de-emphasised for equity. | Mangiola 2024, [DOI 10.1111/tan.70000](https://doi.org/10.1111/tan.70000); Gebel 2016, [DOI 10.2215/CJN.07720715](https://doi.org/10.2215/CJN.07720715) |
| **Eurotransplant ETKAS (1996→)** | A, B and DR mismatches counted equally in a match-grade score, plus a mismatch-probability term for hard-to-match phenotypes; 22% of kidneys went out with 0 ABDR mismatches in the first nine years. The ESP old-for-old programme added a DR-compatible arm. | Persijn 2006, [DOI 10.1016/j.humimm.2006.03.008](https://doi.org/10.1016/j.humimm.2006.03.008); Doxiadis 2004, [DOI 10.1097/01.tp.0000103725.72023.d7](https://doi.org/10.1097/01.tp.0000103725.72023.d7) |
| **UK NHSBT (2006 NKAS, retained in the 2019 offering scheme)** | Absolute priority for 000; then four *mismatch levels* built from DR first and B second (A does not define the level); points for age and mismatch are linked so young patients get well-matched kidneys. | Johnson 2010 ([Consensus](https://consensus.app/papers/details/f9c505b4936f559e97ee0defe624cb6a/?utm_source=claude_desktop)); Ali 2026, [DOI 10.1111/ctr.70429](https://doi.org/10.1111/ctr.70429) |
| **Brazil, São Paulo (2002→)** | Explicit per-locus points with a one-vs-two rule: DR 10 (0 MM) / 5 (1 MM); B 4 / 2; A 1 / 0.5. The DR-first rule made DR-homozygous candidates accumulate on the list; a 2022 fix gives them their own pass. | de Marco 2023 ([Consensus](https://consensus.app/papers/details/f6c09ef312325c34b9359ef5db3b1607/?utm_source=claude_desktop)) |
| **Iran (allocation-criteria study)** | A multi-expert fuzzy weighting exercise on the Iranian deceased-donor system put "5 HLA mismatches" at the lowest weight and found the resulting profile "similar to ETKAS". It is a weighting *study*, not the operating rule. | Taherkhani 2019, [DOI 10.1186/s12911-019-0892-y](https://doi.org/10.1186/s12911-019-0892-y) |
| **Living-donor programmes** | The US National Kidney Registry and at least one paediatric programme (Melbourne) already use eplet mismatch in paired-exchange matching; Eurotransplant simulations show PIRCHE-based allocation is feasible without destabilising the list. | Eplet review 2025, [DOI 10.4285/ctr.25.0046](https://doi.org/10.4285/ctr.25.0046); Niemann 2021 ([Consensus](https://consensus.app/papers/details/cbbfa6629b8d5c4999e38b728de31c8b/?utm_source=claude_desktop)) |

Two expert statements push for adding DQ: Tambur et al. 2021 (Kidney Int,
[DOI 10.1016/j.kint.2021.06.026](https://doi.org/10.1016/j.kint.2021.06.026))
and Isaacson et al. 2022 (JASN,
[DOI 10.1681/ASN.2022030296](https://doi.org/10.1681/ASN.2022030296)).
A 2025 survey of 21 national algorithms (Gopal,
[Consensus](https://consensus.app/papers/details/9e1d8da3cd8f5704aa0d702d627b1557/?utm_source=claude_desktop))
found HLA mismatch scoring universal but the weights entirely local.

---

## 4. Evidence by locus

### 4.1 HLA-DRB1 (DR) — rank 1

- **Registry, modern era, per locus.** UK, 25,094 adult deceased-donor
  transplants 2008–2020: a single DR mismatch raised graft failure (SHR 1.119,
  95% CI 1.035–1.211); A, B and DQ mismatches did not. Ten-year graft survival
  was 13% lower with one DR mismatch and 17% lower with two. The UK four-level
  grouping stratified incrementally (levels 3 and 4: +13% and +19%). Benefit was
  absent in Black recipients, which the authors attribute to low-resolution
  typing. Ali 2026, [DOI 10.1111/ctr.70429](https://doi.org/10.1111/ctr.70429).
- **Paired-kidney (near-causal) design.** Eurotransplant Senior Programme, 675
  kidneys from donors ≥65 split between a DR-compatible arm and a no-matching
  arm: DR matching cut 5-year mortality (HR 0.71) and graft failure at one year
  (HR 0.55) and five years (HR 0.73), at the cost of one hour more cold
  ischaemia. de Fijter 2023,
  [DOI 10.1016/j.kint.2023.05.025](https://doi.org/10.1016/j.kint.2023.05.025).
- **UNOS, tacrolimus/MMF era (conference abstracts).** Deceased donors
  (n=66,021): one-year rejection OR 1.27 for one DR mismatch and 1.41 for two;
  only *two* DR mismatches predicted graft loss (HR 1.13). Living donors
  (n=28,736): rejection OR 1.51 (one) and 1.85 (two). UK registry living donors
  (n=4,782): graft-failure HR 1.21 (one) and 1.31 (two), no other locus
  significant. Ali 2022,
  [Consensus DD](https://consensus.app/papers/details/9d6c4f9d6bb15a378077754049a80108/?utm_source=claude_desktop),
  [Consensus LD](https://consensus.app/papers/details/37ffee86206d55b1bff90791a4d16742/?utm_source=claude_desktop),
  [Consensus UK](https://consensus.app/papers/details/c4d1aa426d34578d9111147965547ccc/?utm_source=claude_desktop).
- **Class II drives death with a functioning graft too.** CTS, 177,584
  deceased-donor transplants: class II mismatches were more strongly associated
  with infection- and cardiovascular-related death and hospitalisation than
  class I. Opelz & Döhler 2012,
  [DOI 10.1111/j.1600-6143.2012.04226.x](https://doi.org/10.1111/j.1600-6143.2012.04226.x).
- **Repeat DR mismatch is still dangerous in the Luminex era.** CTS second
  transplants 2010–2021 (n=6,711): a repeated DR mismatch raised first-year
  graft loss (HR 1.61; 2.21 if sensitized); class I repeats did not. Pipeleers
  2024, [DOI 10.1016/j.ajt.2024.12.014](https://doi.org/10.1016/j.ajt.2024.12.014).
  Multicentre, no preformed DSA: repeated DRB1/DQB1 mismatch HR 3.75 for
  one-year graft loss, HR 9.89 for DSA; class I repeats nil. van den Broek 2025,
  [DOI 10.1111/tan.70264](https://doi.org/10.1111/tan.70264).
- **Dose in single centres.** First cadaveric grafts, non-sensitized
  (n=655): one-year survival 90 / 82 / 73% and three-month rejection 48 / 64 /
  82% for 0 / 1 / 2 DR mismatches; A and B mismatches did not correlate with
  rejection. Reisaeter 1998
  ([Consensus](https://consensus.app/papers/details/574f23858c06540ebb5e67ef774fa836/?utm_source=claude_desktop)).
  Retransplants (n=2,574): DR mismatch was the top risk factor; 0–4 AB
  mismatches had no effect when DR was matched. Thompson 2003
  ([Consensus](https://consensus.app/papers/details/95b5929190c25dbc9cf38b5cd61c3244/?utm_source=claude_desktop)).
- **Paediatric meta-analysis** (18 studies, 26,018 recipients): two DR
  mismatches vs 0–1 raised graft failure at 1, 3, 5 and 10 years (RR 1.41,
  1.28, 1.21, 1.30). Shi 2017
  ([Consensus](https://consensus.app/papers/details/a2555fe188a85c0090293b3792bfc5d2/?utm_source=claude_desktop)).
- **Counter-evidence to keep in view.** In 189,141 first adult deceased-donor
  transplants the 27 locus permutations of a given mismatch count were "all but
  one equal, independent of locus" — the *total* count carried the signal.
  Williams 2016,
  [DOI 10.1097/TP.0000000000001115](https://doi.org/10.1097/TP.0000000000001115).
  Paediatric recipients of young deceased donors showed no DR effect. Gritsch
  2008 ([Consensus](https://consensus.app/papers/details/def7032b227556dca2cf3e30bf64ab0a/?utm_source=claude_desktop)).
  A 42-patient Iranian living-unrelated series found DR mismatch not
  significant for rejection (P=0.069) — underpowered, but it is the only Iranian
  datum found. Tajik 2006, PMID 18685174.

### 4.2 HLA-DQB1 (DQ) — rank 2

- **Largest registry test of antigen-level DQ.** UNOS 2005–2014, 93,782 first
  transplants: adjusting for ABDR, 1–2 DQ mismatches raised death-censored
  graft loss in *living*-donor recipients (HR 1.18, 1.07–1.30) and in
  deceased-donor recipients with cold ischaemia ≤17 h (HR 1.12), not with longer
  ischaemia; one-year rejection OR 1.13 (DD) and 1.14 (LD). Leeaphorn 2018,
  [DOI 10.2215/CJN.10860917](https://doi.org/10.2215/CJN.10860917).
- **Independent of DR, living donors, two-field typing.** 3,916 living-donor
  pairs, 11 US centres: DQαβ allele mismatch and DR antigen mismatch were each
  associated with all-cause graft failure (aHR 1.14 and 1.15) and death-censored
  failure (1.19 and 1.18); two DQαβ mismatches raised rejection further (aHR
  1.68) *controlling for DR*. The authors propose prioritising DQ over DR in
  living-donor selection. Charnaya 2024,
  [DOI 10.1097/TP.0000000000005198](https://doi.org/10.1097/TP.0000000000005198).
- **Rejection.** ANZDATA (n=788): 1–2 DQ mismatches, any rejection aHR 1.54,
  late rejection 2.85; AMR aHR 2.50 when DR was also mismatched. Lim 2016,
  [DOI 10.2215/CJN.11641115](https://doi.org/10.2215/CJN.11641115).
- **Sensitization.** SRTR relisted patients (n=4,867): each DQ mismatch raised
  the probability of a new unacceptable antigen against the previous donor by
  25% (DD) and 29% (LD), more than any other locus, and DQ unacceptable antigens
  raised cPRA by 23–29%. Isaacson 2022,
  [DOI 10.1681/ASN.2022030296](https://doi.org/10.1681/ASN.2022030296).
- **Molecular level (needs two-field typing).** DQ eplet load is linearly
  associated with dnDSA, rejection and graft failure (Senev 2020,
  [DOI 10.1681/ASN.2020010019](https://doi.org/10.1681/ASN.2020010019));
  single-molecule DR/DQ eplet thresholds define low / intermediate / high risk
  (Wiebe 2018 AJT, [Consensus](https://consensus.app/papers/details/8fd32a4c8e8b5c37bba6e80548518a1d/?utm_source=claude_desktop);
  Davis 2020, [DOI 10.1111/ajt.16290](https://doi.org/10.1111/ajt.16290));
  PIRCHE-II at DRB1/DQB1, not class I, predicts T-cell-mediated rejection and
  failure (Senev 2022, [DOI 10.1053/j.ajkd.2022.04.009](https://doi.org/10.1053/j.ajkd.2022.04.009)).
  Specific DQ antigens differ: DQ7 and DQ9 mismatches carried the highest dnDSA
  hazard in a Thai cohort (Skulratanasak 2025,
  [Consensus](https://consensus.app/papers/details/3f91283e3dd35158b8086e4f5b115219/?utm_source=claude_desktop));
  DQA1*03:02-DQB1*03:03 dominated in a Han Chinese cohort (Huang 2025,
  [DOI 10.1097/TP.0000000000005445](https://doi.org/10.1097/TP.0000000000005445)).
- **The low-resolution caveat.** According to the 2025 HLA-DQ mini-review,
  when low- or intermediate-resolution DQ types were compared with two-field
  sequencing, "HLA-DQ mismatching assessed using the lower resolution typing
  methods was incorrect in 43% of donor-recipient pairs".
  [DOI 10.3389/fimmu.2025.1525306](https://doi.org/10.3389/fimmu.2025.1525306).
  Up to four DQαβ heterodimers can be expressed per donor, so a DQB1-only
  count is a proxy. This is why DQ is ranked *with* DR rather than above it on
  this archive, despite being the more immunogenic locus.
- **Where DQ did not show.** In the UK 2008–2020 registry DQ mismatch
  predicted early rejection but not long-term failure (Ali 2026); in the
  UNOS tacrolimus-era abstracts DQ raised rejection odds (1.19–1.29) but not
  graft survival (Ali 2022).

### 4.3 HLA-B — rank 3

- Ranked above A in the UK levels and the Brazilian points (B 4/2 vs A 1/0.5).
- UNOS living donors (abstract): two B mismatches OR 1.33 for rejection; one
  1.21 (NS). Deceased donors: two B mismatches OR 1.19. Ali 2022 (links above).
- Paediatric living-donor risk index (P-LKDPI): B mismatch aHR 1.27 *per
  mismatch*, above DR's 1.23. Wasik 2019,
  [DOI 10.1111/ajt.15360](https://doi.org/10.1111/ajt.15360).
- Paediatric meta-analysis: 2–4 A+B mismatches vs 0–1, 5-year graft failure RR
  3.17. Shi 2017 (link above).
- In pancreas transplantation B and DR were the loci that predicted rejection;
  A, C and DQ did not. Rudolph 2016,
  [DOI 10.1111/ajt.13734](https://doi.org/10.1111/ajt.13734).

### 4.4 HLA-A — rank 4

- Rejection odds per mismatch 1.16–1.19 in the UNOS abstracts; no
  graft-survival effect in any modern per-locus model retrieved. Ignored by the
  UK level definition and the OPTN points.
- Its one distinctive effect is sensitization: A-locus unacceptable antigens
  raised cPRA about as much as DQ in deceased-donor re-listers (23.1%).
  Isaacson 2022 (link above).

### 4.5 HLA-C — rank 5, mostly through the antibody gate

- CTS, 2,260 deceased-donor transplants typed for C: C mismatch reduced graft
  survival in presensitized recipients (P<0.001) and not at all in the
  non-presensitized (P=0.75); some C epitopes mattered more than others. Tran
  2011, [DOI 10.1097/TP.0b013e318224c14e](https://doi.org/10.1097/TP.0b013e318224c14e).
- C mismatch rides on B: among "favourably matched" UK pairs 67% had a C
  mismatch — 37% when B was matched, 85.5% when B was mismatched; 30% were DQ
  mismatched. Rees & Darke 2003,
  [DOI 10.1016/S0966-3274(03)00017-0](https://doi.org/10.1016/S0966-3274(03)00017-0).
- Class I molecular mismatch (including C) did not predict rejection or failure
  where class II did (Senev 2022, above). DSA against C, DP and DQ can each
  cause rejection alone, worst in retransplants. Khalil 2025,
  [DOI 10.5500/wjt.v15.i2.99952](https://doi.org/10.5500/wjt.v15.i2.99952).
- Conclusion: C keeps a small weight *when typed*, sorts as `UNKNOWN`
  otherwise (80% of profiles), and its real job is inside Gate B once a
  recipient antibody profile exists.

### 4.6 HLA-DP — no baseline weight (V1 §9 stands)

- DPB1 allele-level mismatch did not predict dnDSA or survival, but DPB1
  eplet / Terasaki-epitope mismatch did reduce graft survival (p<0.001). Tang
  2021, [DOI 10.1111/tan.14422](https://doi.org/10.1111/tan.14422).
- Isolated preformed DP-DSA: 65% ABMR, 30% graft loss, HR 9.6. Seitz 2022,
  [DOI 10.1016/j.ekir.2022.07.014](https://doi.org/10.1016/j.ekir.2022.07.014).
  Swiss cohort: isolated DP-DSA carried the same ABMR and graft-loss risk as
  DR-DSA; class II DSA hurt from 500–1000 MFI, class I did not. Frischknecht
  2022, [DOI 10.3389/fimmu.2022.1005790](https://doi.org/10.3389/fimmu.2022.1005790).
  Meta-analysis: de novo DP antibodies OR 3.6 for loss or rejection; preformed
  not significant. Pan 2022
  ([Consensus](https://consensus.app/papers/details/c588ed00d325568284b3c8d7fcb2ca99/?utm_source=claude_desktop)).
- With 34 DPB1-typed profiles, DP stays a DSA-gate concern only.

### 4.7 DRB3/4/5 and DQA1

- No antigen-level outcome study for DRB3/4/5 was retrieved (PubMed sweep,
  0 hits on outcome). They contribute to class II eplet and PIRCHE scores
  (e.g. Wiebe 2018 DRβ1/3/4/5/DQα1β1 comparison,
  [Consensus](https://consensus.app/papers/details/bf3a8cb2201c5d39b0bcb0b5723ae1a7/?utm_source=claude_desktop)).
  Keep the 1-point presence-conflict tie-breaker; matching use of a null
  suffix stays REVIEW until HA-011(b).
- DQA1 matters as half of the heterodimer (§4.2); anti-DQα DSA causes AMR
  (case series, [DOI 10.1016/j.trim.2022.101607](https://doi.org/10.1016/j.trim.2022.101607)).
  With 776 typed profiles, no baseline weight; the heterodimer plugin applies
  only when both DQA1 and DQB1 are two-field.

### 4.8 The dose effect: is the second mismatch worth as much as the first?

| Evidence | Shape |
|---|---|
| Williams 2016 (DD, 189,141): HR 1.13 at 1 mismatch → 1.64 at 6 ([DOI](https://doi.org/10.1097/TP.0000000000001115)); Williams 2017 (LD, 66,596): +44% at 1 → 2× at 6 ([DOI 10.1097/TXD.0000000000000664](https://doi.org/10.1097/TXD.0000000000000664)); paediatric +30% → +92% ([DOI 10.1097/TXD.0000000000000801](https://doi.org/10.1097/TXD.0000000000000801)) | Linear in the total count |
| Ali 2026 (DR, 10-year survival): −13% at 1, −17% at 2 | Concave: first mismatch ≈ 3× the second |
| Ali 2022 (rejection ORs): DR 1.27→1.41 (DD), 1.51→1.85 (LD); DQ 1.19→1.24, 1.22→1.29; B 1.21→1.33 | Mildly concave to linear |
| Reisaeter 1998 (DR): survival 90/82/73, rejection 48/64/82 | Linear |
| Charnaya 2024 (DQαβ): two mismatches aHR 1.68 for rejection beyond one | Second DQ mismatch still costly |
| OPTN points: 0-DR 2 pts, 1-DR 1 pt; Brazil: DR 10/5, B 4/2, A 1/0.5 | Linear per mismatch, zero valued |
| ESP DR-compatible arm; UK level 2 needs 0 DR | Zero-DR premium |

Reading: price each mismatch, and add a bonus for a full match at DR and DQ.
That reproduces the concave DR curve and the zero-DR premium of every scheme
without inventing a per-locus exponent no paper reports.

### 4.9 Living donors specifically

The Iranian archive is living-donor. Living-donor grafts outlive deceased-donor
grafts at every mismatch level, yet HLA mismatch still counts *inside* the
living-donor pool: linear hazard (Williams 2017), DQ effect present in LD and
not in long-ischaemia DD (Leeaphorn 2018), DQ and DR independent (Charnaya
2024), DR the only locus with a survival signal in UK LD (Ali 2022). Preformed
DSA hurt less after living than deceased donation (Kamburova 2018,
[Consensus](https://consensus.app/papers/details/ebbd4dd195eb5b86bae3d2778051e48b/?utm_source=claude_desktop)),
but donor quality (age, eGFR, BMI, blood pressure) is the larger term in the
living-donor risk indices (Massie 2016 LKDPI,
[DOI 10.1111/ajt.13709](https://doi.org/10.1111/ajt.13709); Wasik 2019). HLA is
one axis of a living-donor choice, not the whole of it — the platform's
"next clinical action" field should say so.

---

## 5. The "best-performing algorithms", and why V2 cannot run them

| Method | What it models | Best evidence | Needs |
|---|---|---|---|
| HLAMatchmaker eplets (single-molecule DR/DQ thresholds) | B-cell epitopes | AUC 0.84 vs 0.54 for antigen matching (Wiebe 2018); DQ eplet load linear with dnDSA/failure (Senev 2020); DR/DQ risk categories (Davis 2020) | Two-field typing |
| PIRCHE-II | Indirect T-cell epitopes | HR 1.13 per ln for failure (Geneugelijk 2018, [DOI 10.3389/fimmu.2018.00321](https://doi.org/10.3389/fimmu.2018.00321)); DRB1/DQB1 only (Senev 2022); dnDSA at score >9 (Lachmann 2017, [Consensus](https://consensus.app/papers/details/0b79d572dbfa5ac28ff50de725e99773/?utm_source=claude_desktop)) | Two-field typing; licensed service |
| EMS-3D, HLA-EMMA, Snow | Physicochemical / solvent-accessible mismatch | Comparable to eplets (Wiebe 2018 Transplantation); Snow+PIRCHE doubled dnDSA prediction accuracy (Chou-Wu 2025) | Two-field typing |
| B-cell + T-cell combination | Both pathways | SRTR >400,000 transplants: complementary, best classification (Niemann, per the 2025 eplet review) | Two-field typing |
| Amino-acid / ML (FIBERS) | Data-driven bins | HR 1.10 beyond antigen mismatch; DRB1 the strongest locus (Dasariraju 2023, [Consensus](https://consensus.app/papers/details/bbfc1939dcfb5efeb9eff7ac9a35bc20/?utm_source=claude_desktop)) | Imputed alleles |

All of these require two-field typing. Registries obtain it by imputation, and
the 2025 eplet review reports that imputation keeps the risk class in >90% of
pairs but misassigns 23% of DSA specificities (Senev). The constitution forbids
imputation for clinical output; V1 §8 allows it only in a research namespace.
So the archive supports an **antigen-level** pre-screen, and molecular scoring
becomes possible only for pairs whose lab reports are two-field (a handful
today) or after re-typing.

The 2025 scoping review of 98 eplet studies (284,540 recipients) found class
II eplet mismatch consistently associated with dnDSA, AMR and graft loss in
kidney, with class I associations weaker and heterogeneous, and only 16% of
studies using true high-resolution typing. Stögner 2025,
[DOI 10.3389/frtra.2025.1710058](https://doi.org/10.3389/frtra.2025.1710058).

---

## 6. Proposal for policy v2 (`IR-KIDNEY-MATCH-2.0.0`, PRE_SCREENING_ONLY)

Nothing below is adopted. It is the evidence-shaped starting point for the
HA-004 conversation and for a policy version bump.

### 6.1 Ranking tuple (changes to V1 §5 in bold)

1. immunologic blocker status (unchanged);
2. crossmatch stage (unchanged);
3. **HLA-DRB1 mismatch** (was DQ);
4. **HLA-DQB1 mismatch, or DQαβ when both chains are two-field** (was DRB1);
5. class II burden (unchanged);
6. B; 7. A; 8. C **(C sorts `UNKNOWN` after 2 — never as 0)**; 9. total burden;
10. evidence-quality penalty; 11. unknown-field count; 12. freshness; 13. stable ID.

Why swap 3 and 4: DR carries the graft-survival evidence and the allocation
precedent, and its antigen-level count is reliable at one-field resolution; DQ
carries the dnDSA/AMR evidence but its antigen-level count is wrong in ~43% of
low-resolution pairs. On two-field data the order can revert (Charnaya 2024
argues DQ-first for living donors). This is the single largest judgement call
in the proposal and is listed as decision M1 below.

### 6.2 Tie-breaker coefficients (V1 §6 replacement, admin-only)

`penalty = Σ_locus ( w_locus × mismatches_locus ) − Σ_locus ( bonus_locus × [mismatches_locus = 0 and locus typed] )`

| Locus | w per mismatch | zero-mismatch bonus | cost 0 / 1 / 2 | second ÷ first | V1 was |
|---|---|---|---|---|---|
| DRB1 | 4 | 2 | 0 / 6 / 10 | 0.67 | 4 |
| DQB1 (or DQαβ) | 4 | 1 | 0 / 5 / 9 | 0.80 | 5 (6 for DQαβ) |
| B | 2 | 0 | 0 / 2 / 4 | 1.0 | 2 |
| A | 1 | 0 | 0 / 1 / 2 | 1.0 | 1 |
| C (only when typed on both sides) | 1 | 0 | 0 / 1 / 2 | 1.0 | 1 |
| DRB3/4/5 presence conflict | 1 | — | — | — | 1 |
| DQA1 alone, DPA1, DPB1 | 0 | — | — | — | 0 |

Ratios are set to the published effect sizes, not to a formula: DR ≈ 2 × B ≈
4 × A on rejection odds (Ali 2022) and on the Brazilian points; DQ level with
DR on living-donor graft failure (Charnaya 2024) minus a step for
low-resolution unreliability; the DR bonus reproduces the concave 10-year
curve (Ali 2026) and the OPTN 0-DR premium; the smaller DQ bonus reflects that
the second DQ mismatch still adds risk (Charnaya 2024). An `UNKNOWN` locus
contributes nothing to the penalty and is counted in tuple step 11, so a
donor with fewer typed loci never looks better than one fully typed.

### 6.3 Gates and outputs

- Gate B must label every pair `ANTIBODY_UNKNOWN` today and make it visually
  loud: the evidence on C (Tran 2011) and on repeat mismatches (Pipeleers 2024,
  van den Broek 2025) says sensitization changes which loci matter.
- Add a **repeat-mismatch flag** for recipients with a prior transplant
  (donor antigen equals a previous donor's mismatched DR or DQ) — a hard
  `REVIEW` rather than a weight, given HR 1.6–3.8.
- Add a **recipient homozygosity note** at DR and DQ (a homozygous recipient
  can reach zero mismatches only from a matching homozygous donor; de Marco
  2023) so the UI does not read a structural 1-mismatch as a poor donor.
- Keep: no percentage, no compensation, explanation reconstructs the tuple.

---

## 7. Decisions this review cannot make (for HA-004 and the operator)

| # | Decision | Default in the proposal | Who |
|---|---|---|---|
| M1 | DR before DQ in the tuple at one-field resolution, or keep V1's DQ-first | DR first | immunologist (HA-004) |
| M2 | Zero-mismatch bonus at DR (2) and DQ (1) | yes | immunologist |
| M3 | C weight 1 when typed, `UNKNOWN` otherwise; no imputing C from B haplotypes | yes | immunologist |
| M4 | DRB3/4/5 null suffix in matching | stays REVIEW (HA-011(b)) | immunologist |
| M5 | Whether Iranian labs report serologic or molecular DQ, and at what field depth | unknown | immunologist / lab |
| M6 | Whether a two-field re-typing path exists for shortlisted pairs (unlocks §5) | unknown | operator |
| M7 | Policy version bump 1.0.0 → 2.0.0 with the coefficients in a versioned file | after M1–M3 | operator |

---

## 8. Gaps and cautions

- No Iranian outcome data were found beyond one 42-patient series; the
  ethnicity-specific findings (Ali 2026) say low-resolution DR matching can
  fail to deliver its benefit in some populations. The coefficients must be
  recalibrated on local outcomes before any clinician-reliability claim (V1 §6).
- Non-HLA incompatibility carries independent risk (nsSNP mismatch HR 1.68 per
  IQR; Reindl-Schwaighofer 2019,
  [DOI 10.1016/S0140-6736(18)32473-5](https://doi.org/10.1016/S0140-6736(18)32473-5))
  — out of scope, worth naming so no one reads an HLA rank as a full risk.
- Donor quality dominates living-donor graft survival in the risk indices;
  the platform must not present the HLA rank as a donor ranking.
- Several key living-donor numbers (Ali 2022) are conference abstracts; treat
  them as supporting, not primary.

---

## 9. Reference list (retrieved 2026-09-07)

PubMed (DOI): Williams 2016 10.1097/TP.0000000000001115 · Williams 2017
10.1097/TXD.0000000000000664 · Williams 2018 10.1097/TXD.0000000000000801 ·
Opelz & Döhler 2007 10.1097/01.tp.0000269725.74189.b9 · Opelz & Döhler 2012
10.1111/j.1600-6143.2012.04226.x · Süsal & Opelz 2013
10.1097/MOT.0b013e3283636ddf · Ali 2026 10.1111/ctr.70429 · de Fijter 2023
10.1016/j.kint.2023.05.025 · Pipeleers 2024 10.1016/j.ajt.2024.12.014 ·
van den Broek 2025 10.1111/tan.70264 · Leeaphorn 2018 10.2215/CJN.10860917 ·
Lim 2016 10.2215/CJN.11641115 · Charnaya 2024 10.1097/TP.0000000000005198 ·
Isaacson 2022 10.1681/ASN.2022030296 · Tambur 2021 10.1016/j.kint.2021.06.026 ·
Wong 2025 10.1016/j.humimm.2025.111345 · Tran 2011 10.1097/TP.0b013e318224c14e ·
Rees & Darke 2003 10.1016/S0966-3274(03)00017-0 · Khalil 2025
10.5500/wjt.v15.i2.99952 · Tang 2021 10.1111/tan.14422 · Seitz 2022
10.1016/j.ekir.2022.07.014 · Daniëls 2020 10.1016/j.trim.2020.101287 ·
Frischknecht 2022 10.3389/fimmu.2022.1005790 · Huang 2025
10.1097/TP.0000000000005445 · Liu 2022 10.1016/j.trim.2022.101607 · Mangiola
2024 10.1111/tan.70000 · Gebel 2016 10.2215/CJN.07720715 · Persijn 2006
10.1016/j.humimm.2006.03.008 · Doxiadis 2004 10.1097/01.tp.0000103725.72023.d7 ·
Taherkhani 2019 10.1186/s12911-019-0892-y · Tajik 2006 PMID 18685174 · Wasik
2019 10.1111/ajt.15360 · Massie 2016 10.1111/ajt.13709 · Foster 2013
10.1097/TP.0b013e318298f9db · Kamoun 2017 10.1097/TP.0000000000001670 ·
Reindl-Schwaighofer 2019 10.1016/S0140-6736(18)32473-5 · Rudolph 2016
10.1111/ajt.13734 · HLA-DQ mini-review 2025 10.3389/fimmu.2025.1525306 ·
Eplet review 2025 10.4285/ctr.25.0046 · Stögner 2025
10.3389/frtra.2025.1710058 · Senev 2020 10.1681/ASN.2020010019 · Davis 2020
10.1111/ajt.16290 · Senev 2022
10.1053/j.ajkd.2022.04.009 · Geneugelijk 2018 10.3389/fimmu.2018.00321 · Lee
2022 10.3390/ijms23137357 · Bezstarosti 2023 10.1111/tan.15008.

Consensus index (conference abstracts and papers without a retrieved DOI):
Ali 2022 (three abstracts), Thompson 2003, Reisaeter 1998, Shi 2017, de Marco
2023, Johnson 2010, Gopal 2025, Niemann 2021, Dasariraju 2023, Wiebe 2013 /
2018 (two), Pan 2022, Lachmann 2017, Kamburova 2018, Skulratanasak 2025,
Gritsch 2008 — links inline above.
