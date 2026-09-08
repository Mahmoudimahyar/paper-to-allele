# The shape of the HLA mismatch penalty in living-donor kidney transplantation

## A systematic evidence review, with a derived scoring model for a low-resolution pre-screen

**Version:** 2.0 (supersedes `HLA_MATCHING_EVIDENCE_2026-09-07.md`)
**Date:** 2026-09-08
**Status:** EVIDENCE REVIEW. Decides nothing. Any change to `MATCHING_POLICY_V1.md`
is a policy version change and is blocked by HA-004.

---

## Summary

A first version of this review proposed a scoring model with a constant penalty
per HLA mismatch at each locus. That proposal was wrong, and this review
documents why.

An additive point score is a log-linear model: it assumes that the *n*-th
mismatch multiplies the hazard by the same factor as the first. The registry
evidence does not have that shape. The two largest analyses of the question fit
a straight line on the **hazard-ratio** scale, not the log-hazard scale, and
report an **intercept above one**. Both features contradict a constant-weight
score, and both point the same way: **the penalty belongs to the first mismatch,
not to the count.**

Three findings drive the revised model.

1. **The dose-response is concave in log-hazard.** Extrapolating the first
   mismatch's effect multiplicatively — exactly what a constant per-mismatch
   penalty does — overstates the risk of a six-mismatch donor by 27% in
   deceased donors and by an order of magnitude in living-unrelated donors.

2. **There is a step at zero mismatches, and it is a living-donor phenomenon.**
   The fitted intercept is 1.04 in deceased donors, 1.28 in all living donors,
   1.20 in living-related and **1.47 in living-unrelated** donors. Since the
   hazard ratio at zero mismatches is 1.00 by construction, an intercept of 1.47
   is a discontinuity: in living-unrelated donation the gap between a full match
   and any mismatch is worth about 2.9 additional mismatches' worth of slope.

3. **Per locus, the second mismatch costs about a third of the first.** Across
   eight independent series at HLA-DR the ratio of the second mismatch's
   log-effect to the first's has a median of 0.29 (range 0.23–0.49); at HLA-DQ
   the median is 0.33; at HLA-B, 0.50. Not one series is consistent with a
   constant weight.

4. **The loci are not independent, so the score cannot be a plain sum.** In
   39,205 Eurotransplant transplants the benefit of class I matching existed
   only among DR-matched pairs, and a single DR incompatibility abolished it.
   HLA-DR gates the value of matching anything else.

The Iranian archive is a living-**unrelated** donor population, which is the
stratum where the step at zero is largest and where HLA matching carries the
most weight. The revised model is therefore not a linear score with a small
bonus. It is a **full-match bonus that dominates, a shallow taper above it, and
a DR gate on the remaining loci.**

The review rests on **99 kidney-transplant papers and 1,134 extracted effect
sizes**. Of 567 supporting quotes, 549 were re-matched verbatim against cached
source text by a deterministic script; 15 more could not be re-matched because
no source was cached and are flagged as lower-confidence; 3 failed and are
withheld, together with the paper they came from (§9). Appendix A carries the
per-paper record.

Two caveats bound the confidence. The living-unrelated one-mismatch hazard
ratio is 1.79 with a 95% confidence interval of 0.86 to 3.76 — not significant —
and the intercept interval is 0.90 to 2.03. The direction is consistent across
all three living-donor strata; the magnitude is not precisely estimated. And no
Iranian outcome cohort of adequate size models HLA mismatch at all, so HA-004
still governs.

---

## 1. Question and constraints

The operator asked which loci matter more, whether both alleles must match at
some loci, how much the second mismatch should weigh, and challenged the
linearity of the first proposal.

The system this evidence feeds is a **pre-screen**, not a clinical decision.
Constraints from the constitution and MATCH-001 that bound any answer:

- ABO, donor-specific antibody and crossmatch gates precede any HLA heuristic;
  a missing value is `UNKNOWN`, never zero mismatch.
- No high-resolution inference from low-resolution typing.
- No compatibility percentage; a lexicographic ordering with a versioned,
  admin-only numeric tie-breaker.
- Matching never reads compensation data.
- HA-004: Iranian histocompatibility practice must be confirmed before the
  matching specification is frozen.

### What the data can support

Measured from the Gold database on 2026-09-08 (counts only):

| | Profiles |
|---|---|
| Gold profiles (unique photographs) | 19,200 |
| …carrying at least one HLA value | 14,864 |
| HLA-A / HLA-B / HLA-DRB1 typed | 12,131 / 11,602 / 12,258 |
| HLA-DQB1 typed | 12,234 |
| HLA-C typed | 3,794 |
| HLA-DQA1 / DPB1 / DPA1 typed | 776 / 34 / 26 |
| A, B and DRB1 all present | 9,817 |
| A, B, C, DRB1 and DQB1 all present | 2,678 |
| ABO known | 8,792 |
| Antibody, panel-reactive antibody or crossmatch data | none |

Typing resolution is one-field on 97% of stored values. Every typed locus
carries both alleles. Three consequences bind the design: no molecular
(eplet, PIRCHE-II, electrostatic) method can run, because all of them require
two-field typing and imputation is forbidden for clinical output; HLA-C is
`UNKNOWN` for four profiles in five and must sort as unknown rather than as
zero; and every pair is `ANTIBODY_UNKNOWN`, which matters because the evidence
below shows that sensitisation is what turns a minor locus into a major one.

---

## 2. Methods

See `docs/clinical/HLA_EVIDENCE_METHODS_2026-09-08.md` for the full protocol.
In brief: PubMed and PubMed Central, plus the Consensus index until its monthly
quota was exhausted, searched on 7–8 September 2026. Eight parallel search
strands ran 238 PubMed queries across the dose-response shape, per-locus
estimates, locus interactions, effect modifiers, molecular mismatch, allocation
algorithms, Iranian and regional evidence, and statistical modelling. Ninety-two
candidate papers were returned and merged with a seed list of 52, giving 104
papers for extraction. Five were excluded after extraction — four failed the
kidney-only or HLA-exposure test, and one Iranian cohort proved unretrievable —
leaving **99 papers** and 1,134 effect sizes in the review.

Eligibility was **kidney transplantation only** — pancreas-kidney, liver, heart
and lung papers were excluded — reporting HLA mismatch as an exposure, or the
modification of its effect, or an allocation algorithm's HLA component.

One extraction agent per paper filled a fixed contract from PubMed Central full
text where available: scope, a relevance argument, every effect size with its
confidence interval and location in the paper, the dose-response series exactly
as printed, interactions, and three to six verbatim quotes of at most 40 words
each. Numbers absent from the retrieved text were recorded as absent, never
inferred.

Verification is deterministic rather than agent-based: a script re-matched every
quote against the source text its agent had cached, folding only typographic
variation (Unicode dashes, curly quotes, a stray space before punctuation) and
unit-tested to confirm that a paraphrase still fails. A quote differing by one
word fails and is withheld. This replaced a planned second-agent refutation pass
because agent verifiers were the first work lost to usage limits, and because
the script covers every quote in every paper. It found that one paper's quotes
matched no retrievable source (§9).

---

## 3. Results: the shape of the penalty

### 3.1 An additive score assumes a shape the data do not have

A score that charges *w* points per mismatch and ranks by the total is a
log-linear model of risk: total points are proportional to log hazard, so
*HR(k) = exp(bk)*, and each additional mismatch multiplies the hazard by the
same factor.

The two largest analyses of HLA mismatch count in kidney transplantation fit a
different curve. Both fitted an ordinary least-squares line to the Cox hazard
ratios **on the hazard-ratio scale**:

> "A significant linear relationship of hazard ratios was associated with HLA
> mismatch and affects allograft survival even during the recent periods of
> increasing success in renal transplantation."
> — Williams 2016, Abstract ([DOI 10.1097/TP.0000000000001115](https://doi.org/10.1097/TP.0000000000001115))

That is linearity in *HR*, not in *log HR*. The distinction is not cosmetic. A
line in the hazard ratio is concave in log-hazard, so a constant per-mismatch
penalty systematically over-charges poorly matched donors.

**Table 1. What a constant-weight score predicts versus what was observed.**

| Population | n | HR at 1 mismatch | Constant-weight prediction at 6 (HR¹⁶) | Observed HR at 6 | Overstatement |
|---|---|---|---|---|---|
| Deceased donors | 189,141 | 1.13 | 2.08 | 1.64 | 27% |
| All living donors | 66,596 | 1.44 | 8.92 | 2.12 | 321% |
| Living related | 40,596 | 1.42 | 8.20 | 2.03 | 304% |
| **Living unrelated** | **26,000** | **1.79** | **32.89** | **2.57** | **1180%** |

Deceased-donor figures from Williams 2016; living-donor figures from Williams
2017 ([DOI 10.1097/TXD.0000000000000664](https://doi.org/10.1097/TXD.0000000000000664)):

> "In fully adjusted analyses of 26 000 LU donor transplants, there was a 79%
> higher risk (HR, 1.79; 95% CI, 0.86-3.76) of allograft failure for 1 mismatch
> as compared with 0 mismatch, which did not obtain statistical significance
> while a 2.57 (1.43-4.61) fold higher risk was observed for 6 mismatches."
> — Williams 2017, Results

The error grows with the population's relevance to this project: it is smallest
in deceased donors, largest in living-unrelated donors.

### 3.2 The step at zero mismatches, and why it is a living-donor finding

Both papers report the fitted line's **intercept**. Because the hazard ratio at
zero mismatches is 1.00 by construction, an intercept above 1.00 means the curve
does not pass through the origin: there is a discontinuity between a full match
and one mismatch that the slope does not explain.

**Table 2. Fitted line, by donor stratum (fully adjusted models).**

| Stratum | n | Intercept *a* (95% CI) | Slope *c* (95% CI) | Step *a*−1 | Step, in units of slope |
|---|---|---|---|---|---|
| Deceased donors | 189,141 | 1.04 (1.00–1.08) | 0.11 (0.09–0.12) | 0.04 | 0.4 |
| All living donors | 66,596 | 1.28 (0.94–1.61) | 0.15 (0.06–0.24) | 0.28 | 1.9 |
| Living related | 40,596 | 1.20 (0.92–1.48) | 0.19 (0.09–0.29) | 0.20 | 1.1 |
| **Living unrelated** | **26,000** | **1.47 (0.90–2.03)** | **0.16 (0.04–0.29)** | **0.47** | **2.9** |

> "for the fully adjusted regression, the slope is 0.15 (0.06-0.24) with an
> intercept of 1.28 (0.94-1.61)"
> — Williams 2017, Results, all living donors

> "LU allografts represent the smallest stratum in the analysis and have a slope
> for the reduced model of 0.16 (0.04-0.28) with an intercept of 1.41
> (0.84-1.98), whereas for the full Cox regression HRs, the slope is 0.16
> (0.04-0.29) with an intercept of 1.47 (0.90-2.03)"
> — Williams 2017, Results, living-unrelated stratum

The same paper states the ordering explicitly:

> "The penalty in HR for HLA mismatch appears to be least for deceased donors,
> more for the LR fitted line, and largest for the LU stratum."
> — Williams 2017, Results

Two things follow for this project. HLA matching matters **most** in the
living-unrelated setting, which is precisely the Iranian programme's structure.
And within that setting, most of the penalty is spent crossing from zero
mismatches to one.

Expressed as the model the evidence supports for living-unrelated donors:

```
HR(0) = 1.00                          (reference)
HR(k) = 1.47 + 0.16·k     for k ≥ 1   (Williams 2017, LU stratum, full model)
```

On the log scale, the step from zero to one mismatch accounts for **55%** of the
entire penalty across the 0-to-6 range. The remaining five mismatches share the
other 45%.

**The deceased-donor counter-evidence, which sharpens rather than weakens this.**
A 2026 registry analysis asked directly whether the zero-mismatch priority in the
US allocation system is still justified. In 122,951 transplants (6,228 with zero
A/B/DR mismatch), the unadjusted advantage was substantial — hazard ratio 0.788
(0.737-0.841) — but after adjustment it shrank to 0.898 (0.834-0.967), and the
authors concluded that

> "zero HLA ABDR-mismatch confers a small graft survival benefit but no patient
> survival benefit"
> — Keith 2026, Kidney360

with adjusted seven-year graft survival of 67% versus 65%.

That is a small step, and it is a **deceased-donor** cohort — exactly where
Williams 2016 also found a small step (intercept 1.04). The two independent
analyses agree. The claim in this review is not that a zero-mismatch premium is
universally large; it is that the premium is **stratum-dependent**, small in
deceased donation and large in living-unrelated donation, and the archive's
population is the latter.

### 3.3 Per locus: the second mismatch costs about a third of the first

The total-count analyses cannot say which locus to charge. For that, the review
used every study that reports one-versus-zero and two-versus-zero at a single
locus in the same model. The quantity of interest is the ratio of the second
mismatch's log-effect to the first's:

*r* = [log E(2) − log E(1)] / log E(1)

where *r* = 1 means a constant weight is correct, *r* < 1 means concave (the
first mismatch dominates) and *r* > 1 means convex (both alleles must match).

**Table 3. Second-versus-first mismatch, per locus.**

| Study | Population | Outcome | Locus | E(1) | E(2) | *r* |
|---|---|---|---|---|---|---|
| **Shi 2018 (meta-analysis)** | **23 studies, 486,608** | **overall graft failure** | **DR** | **1.12** | **1.15** | **0.23** |
| Ali 2026 | deceased, 25,094 | graft failure (SHR) | DR | 1.119 | 1.148 | 0.23 |
| Ali 2026 | deceased, 25,094 | graft failure (Table 2) | DR | 1.141 | 1.186 | 0.29 |
| Ali 2026 | deceased, 25,094 | graft failure, 10-year | DR | 1.13 | 1.17 | 0.28 |
| Charnaya 2024 | living, 3,916 | rejection | DR (antigen) | 1.86 | 2.17 | 0.25 |
| Ali 2022* | deceased, 66,021 | rejection | DR | 1.27 | 1.41 | 0.44 |
| Ali 2022* | living, 28,736 | rejection | DR | 1.51 | 1.85 | 0.49 |
| Ali 2022* | living UK, 4,782 | graft failure | DR | 1.21 | 1.31 | 0.42 |
| Charnaya 2024 | living, 3,916 | rejection | DQ (αβ, two-field) | 1.82 | 2.25 | 0.35 |
| Charnaya 2024 | living, 3,916 | rejection | DQ (antigen) | 1.39 | 1.55 | 0.33 |
| Ali 2026 | deceased, 25,094 | rejection, DR-matched only | DQ | 1.36 | 1.80 | 0.91 |
| Ali 2022* | deceased, 66,021 | rejection | DQ | 1.19 | 1.24 | 0.24 |
| Ali 2022* | living, 28,736 | rejection | DQ | 1.22 | 1.29 | 0.28 |
| Ali 2026 | deceased, 25,094 | graft failure (Table 2) | B | 1.082 | 1.146 | 0.73 |
| Ali 2026 | deceased, 25,094 | graft failure, 5-year | B | 1.16 | 1.24 | 0.45 |
| Ali 2022* | living, 28,736 | rejection | B | 1.21 | 1.33 | 0.50 |
| Ali 2022* | deceased, 66,021 | rejection | A | 1.16 | 1.18 | 0.12 |

\* congress abstract, supporting evidence only.

**Medians: DR 0.29 (eight series), DQ 0.33 (five), B 0.50 (three), A 0.12 (one).**

The meta-analytic estimate is the most important row. Pooling 23 studies and
486,608 recipients, one DR mismatch carried 12% higher risk of graft failure and
two carried 15% — the second mismatch adding a fifth of what the first did:

> "compared with 0 DR-mismatches, 1 and 2 mismatches were significant associated
> with 12 and 15% higher risk of overall graft failure, respectively"
> — Shi 2018, BMC Nephrology

The same meta-analysis puts the pooled per-mismatch effect across loci at a
hazard ratio of 1.06 (1.05–1.07), falling to 1.04 (1.02–1.05) in cohorts of
10,000 or more — a reminder of how small the antigen-level signal is once
pooled.

Every series is concave. Not one is consistent with a constant weight. One
further ratio, from Ali 2026's HLA-DQ graft-failure estimates (1.031 and 1.080,
both non-significant), was excluded: with the first estimate barely above 1.00
the denominator approaches zero and the ratio is numerically unstable.

The finding is corroborated in words by the largest contemporary per-locus
registry analysis:

> "Ten-year graft survival was 13% less with one HLA DR mismatch, and 17% less
> with 2 HLA DR mismatch, in comparison to zero DR mismatch."
> — Ali 2026, Abstract ([DOI 10.1111/ctr.70429](https://doi.org/10.1111/ctr.70429))

Thirteen points of the seventeen arrive with the first mismatch.

### 3.4 What this means for the score

A pre-screen that ranks donors is free to use any monotone function of risk. But
if the tie-breaker is a sum of per-locus penalties, that sum should approximate
log hazard, and the evidence says the log-hazard curve is a **step followed by a
shallow taper**, not a ramp.

Concretely, the weights implied by the fitted lines, normalised so the first
mismatch is 1.00:

| Stratum | 1st | 2nd | 3rd | 4th | 5th | 6th |
|---|---|---|---|---|---|---|
| Deceased donors | 1.00 | 0.91 | 0.83 | 0.77 | 0.71 | 0.67 |
| All living donors | 1.00 | 0.90 | 0.82 | 0.75 | 0.69 | 0.64 |
| Living related | 1.00 | 0.87 | 0.77 | 0.69 | 0.63 | 0.58 |
| Living unrelated | 1.00 | 0.91 | 0.83 | 0.76 | 0.71 | 0.66 |

That taper is the *within-count* effect and is mild. The large effect is the
step at zero (Table 2) and the per-locus concavity (Table 3), both of which say
the same thing in different units: **reward a fully matched locus; do not charge
linearly for the count.**

---

### 3.5 The cleanest test: a pure step, not a ramp

The strongest single result on this question comes from a cohort typed at
two-field resolution, which lets the antigen count and the molecular load be
compared in the same 664 recipients.

> "Traditional HLA-DR/DQ whole antigen mismatch greater than zero was associated
> with significantly lower HLA-DR/DQ dnDSAfree survival (= .0003). However,
> there was no statistical difference in HLA-DR/DQ dnDSAfree survival between
> HLA-DR/DQ whole antigen risk groups other than zero (= .48, FigureA). This was
> also true in a locus-specific analysis of HLA-DR or HLA-DQ dnDSA development."
> — Wiebe 2019, Results 3.2

Zero versus non-zero separates the cohort (p = 0.0003). Among the non-zero
groups there is no separation at all (p = 0.48), and that holds locus by locus.
At antigen level the relationship is not a ramp with slight curvature; within
the resolution this project has, it is a **step**.

The same paper measures how little the antigen count carries: as a correlate of
de novo donor-specific antibody it reaches an area under the curve of **0.54 for
HLA-DR and 0.58 for HLA-DQ**, barely above chance, against 0.84 for a
single-molecule eplet threshold.

### 3.6 Why the antigen curve is concave when the molecular curve is not

The molecular literature shows the opposite shape. In 926 donor-recipient pairs,
antibody-verified HLA-DQ eplet mismatch load behaved as a straight line in the
log-hazard with no threshold at which risk stopped rising:

> "The association with DQ antibody-verified eplet mismatches was linear,
> without a safe threshold"
> — Senev 2020, JASN ([DOI 10.1681/ASN.2020010019](https://doi.org/10.1681/ASN.2020010019))

with the odds of T-cell-mediated and antibody-mediated rejection rising 5% and
12% per antibody-verified DQ eplet mismatch.

The two shapes are consistent, and their relationship explains the concavity.
Eplet load is the quantity the immune system responds to, and its effect is
approximately linear. The antigen count is a coarse proxy for it. Crossing from
zero to one antigen mismatch at a locus introduces a whole mismatched molecule
and with it most of that locus's eplet burden; the second antigen mismatch adds
a molecule that shares many eplets with the first. The antigen count saturates
even though the underlying scale does not.

This has a direct engineering consequence. The concavity is not a quirk of one
registry. It is what a coarse proxy for a linear underlying scale must look
like, and a pre-screen restricted to one-field typing is using that proxy.

### 3.7 Three different questions that get confused

"Is the effect linear?" hides three separate questions, and the literature
answers them differently. Keeping them apart is what makes the evidence
coherent.

**Question 1. Across loci, do the effects add?** Do a mismatch at A and a
mismatch at B together cost what each costs alone?

The classic Collaborative Transplant Study analysis of over 40,000 transplants
says approximately yes:

> "The influence of the three loci was additive so that the survival rate
> difference between transplants with zero or six mismatches for HLA-A, -B, -DR
> was 17% at 5 years."
> — Opelz 1992, Abstract

Three loci at six percentage points each predicts 18%; 17% was observed. The
largest modern analysis agrees, finding 56 of 57 within-count locus permutations
statistically indistinguishable (Williams 2016). Against this, Ali 2026 finds
only DR significant of four loci, and a retransplant series argues the
total-count gradient is an artefact of mixing loci with very different effects,
A and B contributing little and DR a great deal (Thompson 2003). **Contested.**

**Question 2. Within a locus, does the second mismatch cost what the first
costs?** This is what a per-locus weight assumes.

**No, consistently.** Every series in Table 3 is concave, with the second
mismatch costing a median of 0.29 of the first at DR, 0.33 at DQ and 0.50 at B.
Opelz 1992 cannot address this: it reports only zero versus two mismatches per
locus, never the intermediate category, so its additivity claim is about
Question 1 and is silent on Question 2.

**Question 3. Across the total count, is the log-hazard a straight line?** This
is what an additive score assumes.

**No.** The fitted lines are straight on the hazard-ratio scale with intercepts
above 1.0 (§3.1, §3.2), which is a step plus concavity in log-hazard; and in the
cleanest test the non-zero groups do not differ from each other at all (§3.5).

Of the 99 included papers, **33 characterised a shape**; one of those is
excluded because its source could not be verified (§9), leaving 32. At antigen
level — the scale this archive uses:

| Shape reported at antigen level | n | Papers |
|---|---|---|
| Step, threshold, or a zero-mismatch premium then flat or shallow | 13 | Zhou 1993; Reisaeter 1998; Takemoto 2000; Doxiadis 2007; Meier-Kriesche 2009; Willicombe 2012; Foster 2014; Wiebe 2019; Lee 2022; Dasariraju 2023; Caldwell 2024; Lalji 2025; Ali 2026 |
| Concave: monotone with diminishing increments | 3 | Leeaphorn 2018; Ali 2022 (abstracts); Charnaya 2024 |
| Straight in the hazard ratio with intercept above 1, i.e. a step plus log-concavity | 3 | Williams 2016; Williams 2017; Williams 2018 |
| **Additive across loci and approximately linear in the total count** | **1** | **Opelz 1992** |
| **Flat: no dose-response at all** | **1** | **Gritsch 2008** |
| Direction stated qualitatively, no shape | 2 | Lim 2012; Hafeez 2023 |

The two rows in bold are the counter-evidence, and both deserve their weight.
Opelz 1992 is discussed under Question 1 above: its additivity claim is about
*across* loci and it never reports an intermediate mismatch category, so it
cannot speak to the within-locus shape. Gritsch 2008 found no dose-response
whatever in paediatric recipients of young deceased donors — the DR series was
non-monotonic and essentially flat at 71%, 69% and 71% — which is a genuine null
in a population unlike this archive's.

The molecular scale behaves differently, as §3.6 explains: linear in the
log-hazard with no threshold (Senev 2020; Kamoun 2017, whose splines at 5, 10
and 15 amino-acid mismatches produced no significant change in slope; Wiebe
2017), clinically usable thresholds (Wiebe 2013; Lee 2022), graded categories
(Davis 2020; Wiebe 2019; Johnson 2023; Lee 2025), and dampening at high load
(Niemann 2025).

Williams 2016 describes its own effect as "additive", with "each additional
mismatch has the same effect" — but on the **hazard-ratio** scale, where its
fitted line has a constant increment of 0.11 HR units. Read on the log scale a
point score uses, that same line is concave. It is not evidence for a
constant-weight score.

Two further findings come at the question from other directions.

The largest UNOS analysis of DQ found the concavity in the rejection endpoint
and *no* dose-response at all in graft survival: the first mismatch carried most
of the effect (odds ratio 1.22 from zero to one) and the second added little
(1.10 from one to two), while for death-censored graft survival the authors
reported no linear association, so the survival signal rested entirely on the
pooled one-or-two versus zero contrast (Leeaphorn 2018).

Even on the molecular scale the increments dampen at the top of the range:

> "Molecular incompatibility loads appear superlinear with a dampened increase
> in hazard at high load scores, justifying log-transformation of these metrics"
> — Niemann 2025

so the molecular scale is linear through the middle of its range (Senev 2020)
and flattens at the extreme. The antigen count, being a coarser proxy, saturates
much earlier.

---

## 4. Per-locus ranking

Ranked by the strength and consistency of evidence that a locus predicts outcome
at antigen level, adjusted for the other loci.

**The ranking is time-dependent, and that qualifies everything below.** In the
Collaborative Transplant Study analysis of over 40,000 transplants, the loci
were not equal early and were roughly equal later:

> "during the early posttransplant period, HLA-DR mismatches had a stronger
> influence on graft survival than HLA-B mismatches, and HLA-A mismatches had a
> very small influence"
>
> "during the period from 6 months to 5 years post transplantation, all three
> HLA loci had approximately the same influence"
> — Opelz 1992, Abstract

A pre-screen that ranks candidate donors is choosing what to avoid at the
outset, which is the early window where DR dominates. But a ranking that treats
HLA-A as worthless will misstate long-term risk, which is why A keeps a small
non-zero weight below rather than being dropped.

### 4.1 HLA-DRB1 — rank 1

The only locus with a consistent antigen-level graft-survival signal in
contemporary registries. In 25,094 UK deceased-donor transplants (2008-2020),
with all four loci entered as separate one- and two-mismatch terms, only DR
predicted graft failure (sub-hazard ratio 1.119, 95% CI 1.035-1.211, p = 0.005).

The paired-kidney Eurotransplant Senior study is the closest thing to a
randomised test: 675 kidneys from donors aged 65 or over, one of each pair
allocated with DR matching and the contralateral kidney without. DR matching cut
five-year mortality (HR 0.71, 0.53-0.95) and graft failure at one year (0.55,
0.35-0.87) and five years (0.73, 0.53-0.99), at a cost of one hour more cold
ischaemia ([DOI 10.1016/j.kint.2023.05.025](https://doi.org/10.1016/j.kint.2023.05.025)).
Because both kidneys come from the same donor, donor quality is controlled by
design, which is the usual confounder in matching studies.

A repeated DR mismatch still carries risk in the modern antibody-testing era
where class I repeats do not
([DOI 10.1016/j.ajt.2024.12.014](https://doi.org/10.1016/j.ajt.2024.12.014),
[DOI 10.1111/tan.70264](https://doi.org/10.1111/tan.70264)).

**Counter-evidence, stated plainly.** The largest analysis of all found no
locus-specific effect: across 189,141 deceased-donor transplants, 56 of 57
comparisons between locus permutations within a mismatch count were
statistically indistinguishable, and the authors concluded

> "This strongly suggests that, within mismatch category, the effect of the
> mismatch is identical for each locus combination"
> — Williams 2016, Discussion

That is the main argument against per-locus weighting. It is outweighed here for
three reasons: it is a deceased-donor cohort; the single significant exception
ran in the expected direction (two DR mismatches, HR 1.57, versus two A
mismatches, HR 1.27); and the contemporary analyses that model each locus
separately do find DR and not A.

A second null is more pointed, because it is the only paper found that reports a
flat DR series and it says so plainly:

> "Zero HLA-DR-mismatched kidneys had statistically comparable 5-year graft
> survival (71%), to 1-DR-mismatched kidneys (69%) and 2-DR-mismatched kidneys
> (71%)."
>
> "nor was there a 'dose effect' when more HLA antigens were mismatched between
> the donor and recipient"
> — Gritsch 2008, AJT

Its population is paediatric recipients of deceased donors under 35, where donor
age dominated (relative rate of failure 1.32 for donors 35 or older), and its
practical conclusion was that such recipients "should not turn down such kidney
offers to wait for a better HLA-DR-matched kidney". That is a real limit on how
far DR priority should be pushed when it costs waiting time or donor quality —
which is the trade-off a living-donor pre-screen does *not* face, since the
donors are already identified. It does not transfer to this archive, but it is
the strongest published statement that DR matching can be worth nothing.

### 4.2 HLA-DQB1 — rank 2, on a different endpoint

DQ's evidence is strong but attaches to antibody formation and rejection rather
than to antigen-level graft survival.

- In 93,782 UNOS transplants, adjusted for A, B and DR, DQ mismatch raised
  death-censored graft loss in **living-donor** recipients (HR 1.18, 1.07-1.30)
  and in deceased-donor recipients only when cold ischaemia was under 17 hours
  ([DOI 10.2215/CJN.10860917](https://doi.org/10.2215/CJN.10860917)).
- In 3,916 living-donor pairs with two-field class II typing, one and two DQαβ
  mismatches raised rejection (odds ratios 1.82 and 2.25), and two mismatches
  stayed significant with DR in the model
  ([DOI 10.1097/TP.0000000000005198](https://doi.org/10.1097/TP.0000000000005198)).
- Each DQ mismatch raised the probability of returning to the waiting list with
  a new unacceptable antigen against the previous donor by 25.2% (deceased) and
  28.9% (living), more than any other locus
  ([DOI 10.1681/ASN.2022030296](https://doi.org/10.1681/ASN.2022030296)).
- In the UK registry DQ predicted early rejection but not long-term graft
  failure, and the DQ rejection effect persisted among DR-matched recipients
  (odds ratios 1.36 for one mismatch, 1.80 for two).

Two facts hold DQ at rank 2 for this archive: its graft-survival signal is
inconsistent at antigen level, and a one-field DQ mismatch call is the least
reliable of the five loci (§6). The locus matters; the measurement available
here is weak.

### 4.3 HLA-B — rank 3

Ranked above A in the UK mismatch levels and in the São Paulo point system
(B 4/2 versus A 1/0.5). In the UK registry two B mismatches reached significance
for graft failure (HR 1.146, 1.002-1.310) while one did not, and both were
significant in the five-year model. B is the one locus where the second mismatch
approaches the cost of the first (ratio 0.50-0.73), so it is the one locus for
which a near-linear charge is defensible.

**Counter-evidence.** The meta-analysis of 486,608 recipients found no
significant association between HLA-B mismatching and overall graft survival at
all:

> "we did not observe a significant association between HLA-B mismatching and
> overall graft survival (HR: 1.01; 95% CI: 0.90-1.15)"
> — Shi 2018, BMC Nephrology

B's rank here therefore rests on the allocation schemes and on the
rejection-endpoint evidence, not on pooled graft survival. Its two points are
small for that reason, and a reviewer who wanted to set B to zero for
graft-survival purposes could defend it on this evidence.

### 4.4 HLA-A — rank 4, possibly nothing

In the UK registry the point estimates for A were **below** 1.00 (0.911 for one
mismatch, 0.975 for two), and at five years the one-mismatch estimate reached
nominal significance in the protective direction (0.88, 0.78-1.00, p = 0.043).
That is far more likely to be allocation confounding than benefit, but it is not
evidence of harm. A's clearest role is sensitisation, where A-locus unacceptable
antigens raised calculated panel-reactive antibody about as much as DQ.

### 4.5 HLA-C — rank 5, through the antibody gate

In 2,260 deceased-donor transplants typed for C, mismatch reduced graft survival
in presensitised recipients and not at all in the others:

> "HLA-C mismatch was found to be associated with significantly decreased graft
> survival in presensitized (P<0.001) but not in non-presensitized (P=0.75)
> recipients."
> — Tran 2011 ([DOI 10.1097/TP.0b013e318224c14e](https://doi.org/10.1097/TP.0b013e318224c14e))

Every pair in this archive is antibody-unknown, so C cannot be scored as if
sensitisation were excluded. It is typed on 20% of profiles and sorts as
`UNKNOWN` on the rest.

### 4.6 HLA-DP, DQA1, DRB3/4/5 — no baseline weight

DP allele-level mismatch does not predict outcome, but a preformed isolated DP
donor-specific antibody carries the same risk as a DR one. With 34 DP-typed
profiles, DP belongs to the antibody gate, not the score. DQA1 (776 profiles)
matters as half of the DQ heterodimer and needs two-field typing. No
antigen-level outcome study for DRB3/4/5 was found; they keep only the
presence-conflict tie-breaker.

---

## 5. Interactions: the score cannot be a plain sum

**Class I matching helps only when DR is already matched.** This is the largest
and most directly relevant interaction found. In a single-centre series and in
39,205 Eurotransplant transplants:

> "An additional positive effect of HLA-A,B matching was only found in the full
> HLA-DR compatible group."
>
> "In both studies, the introduction of a single HLA-DR incompatibility
> eliminates the HLA-A,B matching effect."
> — Doxiadis 2007, Transplantation

A retransplant series reached the same conclusion from the other end, arguing
that the smooth-looking gradient across zero-to-six total mismatches is an
artefact of mixing loci with very different effects — A and B contributing
little, DR a great deal — rather than an additive per-mismatch effect
(Thompson 2003).

This is a *gated* structure, not a sum: DR first, and class I only counts once
DR is clean. It is exactly what the UK mismatch levels encode, and it is the
strongest argument in the review against adding independent per-locus penalties.

**DR modifies DQ.** In 788 ANZDATA recipients, DR mismatch was a formal effect
modifier of the DQ effect on antibody-mediated rejection:

> "HLA-DR was an effect modifier between HLA-DQ mismatches and risk of AMR
> (P value for interaction =0.02)."
> — Lim 2016 ([DOI 10.2215/CJN.11641115](https://doi.org/10.2215/CJN.11641115))

The DQ effect on antibody-mediated rejection was present in DR-mismatched
recipients and absent in DR-matched ones.

**DQ and DR are collinear.** In the living-donor cohort with two-field typing,
DQ alone gave an adjusted hazard ratio of 1.14 for death-censored graft failure
and DR alone 1.15; with both in the model each fell to 1.08 and lost
significance, which the authors attribute to linkage disequilibrium between the
class II loci. Adding a DR penalty and a DQ penalty double-counts one underlying
haplotype effect.

**The DQ effect itself depends on donor type.** In the 93,782-transplant UNOS
analysis the DQ effect on death-censored graft loss was present in living-donor
recipients (HR 1.18, 1.07-1.30) and absent in deceased-donor recipients (1.05,
0.98-1.12), with a formal **p for interaction below 0.01**; a second interaction
of the same size split deceased-donor recipients by cold ischaemia at 17 hours
(1.12, 1.02-1.27 below; 0.97, 0.88-1.06 above). A weight fitted on
deceased-donor data does not transfer to living donation, in either direction.

**Class I rides on B.** Among UK pairs classed as favourably matched, 66.7% had
a C mismatch: 36.9% of those matched for B and 85.5% of those mismatched for B
(p < 0.0001). A separate C term is largely a second B term.

**The allocation schemes encode this.** The UK scheme does not sum loci; it
defines four levels from DR first and B second. In the UK registry, level 2 (one
DR mismatch with no B mismatch, or no DR mismatch with up to one B mismatch)
carried no excess risk over a perfect match at all (SHR 0.973, 0.863-1.097),
while levels 3 and 4 did (1.132 and 1.190).

---

## 6. What the archive's typing resolution costs

Every molecular method — eplet, PIRCHE-II, electrostatic, amino-acid, Snow —
requires two-field typing, which 97% of the archive lacks, and the constitution
forbids imputing it for clinical output.

**The antigen count is a weak predictor of the mechanism.** As a correlate of de
novo donor-specific antibody, antigen-level mismatch reaches an area under the
curve of 0.54 for HLA-DR and 0.58 for HLA-DQ, against 0.84 for a single-molecule
eplet threshold (Wiebe 2019). That is close to chance for the endpoint that
drives late graft loss.

**Low-resolution typing misassigns donor specificity, and class II worst.** In
262 sensitised patients whose low-resolution split-antigen typing was
adjudicated against two-field high-resolution genotyping:

> "we confirmed the donor specificity of the HLA antibodies in 173/224 (77.2%)
> cases. In the remaining 51 (22.8%) cases of suspected DSA at the LR genotyping
> level, we disproved the donor specificity by 2F-HR genotyping"
>
> "The majority of these misclassified DSAs (n = 51) were against HLA class II
> (70.6%), especially against the HLA-DQ molecule (N = 22; 43.1%)."
> — Senev 2020, AJT

Low-resolution genotyping assigned donor specificity with 79.8% accuracy. This
is the precise basis for treating DQ as the noisiest term in the model at
one-field resolution. (A 2025 mini-review states more broadly that
low-resolution DQ mismatch assessment "was incorrect in 43% of donor-recipient
pairs"; that is a secondary claim about a different comparison and is not relied
on here.)

**Imputation is worse at exactly the loci that matter.** In the same study,
agreement between imputed and real two-field genotypes was **75.3% for class I
and 35.4% for class II**. Imputation may preserve a coarse risk class more often
than it reproduces a genotype, but at class II it cannot support a clinical
claim, which is why the constitution confines it to a research namespace.

**A regional programme measured the cost directly, and it is large.** In 585
living-related transplants at a Pakistani centre, serologic typing was compared
against DNA typing in the same patients:

> "Error rates in serology as compared to PCR-SSP were 24% for HLA A, 16% for
> HLA B and 35% for HLA DR."
> — Zafar 2003, Exp Clin Transplant

The error was worst at the locus that matters most. Progressively better typing
tracked progressively better outcomes across three sequential groups: acute
rejection fell from 39% with serology alone, to 30% with DNA typing at DR, to
26% with DNA typing at A, B and DR (p = 0.02), and one- and three-year graft
survival rose from 81% and 69% to 93% and 87% (p = 0.0001). This is a regional
living-donor programme structurally similar to the Iranian one, and it is the
most direct available evidence that typing quality — not only the matching rule
built on top of it — changes outcomes.

This is the honest ceiling on the exercise: the pre-screen orders donors
sensibly; it does not measure immunological risk. Where typing can be improved,
that buys more than any reweighting of the score.

---

## 7. The Iranian and regional evidence, which is thin

A dedicated search strand ran 28 PubMed queries for Iranian and regional
(Turkey, Pakistan, Gulf, Egypt) kidney-transplant cohorts reporting HLA mismatch
as a variable. **No Iranian cohort of adequate size that models HLA mismatch as
a predictor of graft outcome was found.** This is the single largest gap in the
review and the reason HA-004 governs.

What does exist:

- **Tajik 2006** (Tehran, Hashemi Nejad): 42 living-**unrelated** transplants,
  the correct population but far too small. DR mismatch was not significantly
  associated with acute rejection (p = 0.069), and the authors themselves read
  this as a limitation of power and of the living-unrelated setting rather than
  as evidence of no effect. HLA-DR was typed by PCR-SSP at allele-group
  (one-field) level — the same resolution as this archive.
- **Mohammadzadeh 2022** (Shiraz): not an outcome study, but it establishes that
  an Iranian donor HLA panel exists — allele and haplotype frequencies estimated
  from 523 deceased Iranian donors — and that panel-reactive antibody
  calculators "can differ based on the ethnicity to which they are applied".
  This matters for any future antibody gate.
- **Taherkhani 2019**: an expert-weighting exercise on Iranian allocation
  criteria, not outcome data.
- **Regional living-donor programmes** provide the closest analogues.
  Ghoneim 2001 (Mansoura, over 1,200 living-donor transplants) found the number
  of HLA mismatches to be one of three independent predictors of graft survival.
  Zafar 2003 (Karachi, 585 living-related transplants) supplies the typing-error
  and outcome gradient quoted in §6.

Two consequences. First, every effect size in this review is transported from
North American, European or Australasian registries, and the transport rests on
argument rather than local data. Second, the one Iranian datum in the right
population is null and underpowered, which is not evidence against the model but
is a reminder that it has never been tested where it will be used. Any
calibration claim requires Iranian outcome data that does not yet exist.

---

## 8. The derived model

### 8.1 Ranking tuple (changes from V1 in bold)

1. immunologic blocker status; 2. crossmatch stage;
3. **HLA-DRB1 mismatch** (was DQ); 4. **HLA-DQB1, or DQαβ when both chains are
two-field**; 5. class II burden; 6. B; 7. A; 8. **C, sorting `UNKNOWN` after 2,
never as 0**; 9. total burden; 10. evidence quality; 11. unknown-field count;
12. freshness; 13. stable identifier.

DR moves ahead of DQ because DR's antigen-level graft-survival evidence is
consistent and its one-field mismatch call is reliable, while DQ's is neither.
On two-field data the order should revert.

### 8.2 Tie-breaker, rebuilt around the full-match bonus

V1 charged a constant amount per mismatch and added a small separate bonus. The
evidence inverts the emphasis, and the bonus term is then unnecessary: charging
the *first* mismatch at a locus heavily is arithmetically the same as rewarding
a fully matched locus, and it avoids double-counting. The model is therefore two
charges per locus, not a rate:

```
penalty = Σ_locus [ first_locus × 1(mismatches ≥ 1)
                  + second_locus × 1(mismatches = 2) ]   × gate_locus

gate_DRB1 = 1
gate_other = 1 if DRB1 is matched, else 0.5      (see rule 2)
```

A locus that is untyped on either side contributes nothing and is counted in
tuple position 11 instead.

| Locus | First mismatch | Second mismatch | Second ÷ first | Evidence for the ratio |
|---|---|---|---|---|
| DRB1 | 6 | 2 | 0.33 | median *r* = 0.29 across eight series |
| DQB1 | 4 | 1 | 0.25 | median *r* = 0.33, discounted for one-field unreliability |
| B | 2 | 1 | 0.50 | median *r* = 0.50 |
| A | 1 | 0 | — | one series, *r* = 0.12; no survival signal |
| C (typed only) | 1 | 0 | — | effect confined to presensitised recipients |
| DRB3/4/5 presence conflict | 1 | — | — | tie-breaker only |
| DQA1 alone, DPA1, DPB1 | 0 | — | — | antibody gate only |

Four structural rules matter more than the numbers:

1. **A locus with any mismatch pays most of its charge at the first mismatch**,
   which is the same thing as rewarding a fully matched locus. This reproduces
   the step (§3.2, §3.5) and the per-locus concavity (§3.3).
2. **DR gates the rest.** The marginal value of matching any other locus is
   demonstrated only among DR-matched pairs: class I matching benefit disappears
   once a single DR mismatch is present (Doxiadis 2007, n = 39,205), and the DQ
   effect on antibody-mediated rejection is confined to DR-mismatched recipients
   in the opposite direction (Lim 2016, p for interaction = 0.02). Accordingly
   the B, A and C charges apply at full value when DR is matched and at half
   value when DR is already mismatched.
3. **Class II is charged once, not twice.** DR and DQ are collinear through
   linkage disequilibrium — each falls from about 1.15 to 1.08 and loses
   significance when both enter one model (Charnaya 2024) — so the DQ charge is
   halved when DR is already mismatched, rather than summing two measurements of
   one haplotype.
4. **An `UNKNOWN` locus contributes nothing** and is counted separately in tuple
   position 11, so a less-typed donor never outranks a fully typed one.

Rules 2 and 3 both attenuate other loci once DR is mismatched, which is the
single behaviour the interaction evidence supports most consistently: **once the
dominant locus is lost, the remaining matching buys less.** They are stated
separately because their evidence is separate, and either could be dropped
without the other if HA-004 rejects one.

### 8.3 Worked check against the evidence

The absolute scale is arbitrary — the output is an ordering, never a percentage —
so the model is checked on whether it reproduces the orderings the evidence
requires.

| Donor | Penalty |
|---|---|
| Perfect match | 0.0 |
| One HLA-A mismatch only | 1.0 |
| **Two A and two B mismatches, DR and DQ matched** | **4.0** |
| **One DR mismatch alone** | **6.0** |
| One DR and one DQ mismatch | 8.0 |
| Two mismatches at each of DR, DQ, B and A | 12.5 |

Three checks:

- **A donor with four class I mismatches but a matched DR outranks a donor whose
  only fault is a single DR mismatch** (4.0 versus 6.0). This is the ordering
  Doxiadis 2007 and Thompson 2003 require, and the one a flat per-mismatch score
  gets backwards.
- **The second DR mismatch adds 2.0 against the first mismatch's 6.0**, a ratio
  of 0.33 against the evidence median of 0.29 (§3.3).
- **The first-mismatch charges total 14 points, of which DR holds 6 (43%)**,
  against DR's position as the only locus with a consistent antigen-level
  graft-survival signal (§4.1).

The model is not calibrated to any absolute risk and must not be presented as
such. It is an ordering whose shape follows the published curves.

---

## 9. Limitations

- The living-unrelated stratum, the one matching this archive, has the widest
  intervals: the one-mismatch hazard ratio is 1.79 (0.86-3.76, not significant)
  and the intercept 1.47 (0.90-2.03). The direction is consistent across all
  three living-donor strata; the magnitude is not settled.
- The published dose-response lines were fitted by their authors to Cox point
  estimates by ordinary least squares, not by a within-model trend test or
  spline. No paper found tested departure from linearity formally at antigen
  level.
- Registry studies cannot separate matching from allocation. The Eurotransplant
  paired-kidney design is the only near-causal evidence and is confined to
  donors over 65.
- Two of the per-locus one-versus-two series are congress abstracts.
- Non-HLA genetic incompatibility carries independent risk, and donor quality
  dominates the living-donor risk indices. An HLA rank is not a donor rank.
- No Iranian outcome cohort of adequate size models HLA mismatch.
- **One paper was excluded from every quantitative claim after verification
  failed.** For Ashby 2017 (a living-donor graft-survival calculator, 232,705
  transplants) PubMed Central returns an empty full text, and the extracting
  agent read its table from the publisher's web page instead. Its three quotes
  could not be matched against any retrievable source and are withheld, and its
  numbers are not used, although the agent recorded an arithmetic consistency
  check that they pass. This is a limitation of what could be verified, not a
  finding that the paper is wrong.

---

## 10. Decisions this review cannot make (HA-004)

| # | Decision | Default in the model |
|---|---|---|
| M1 | DR before DQ at one-field resolution | DR first |
| M2 | Full-match bonus structure replacing linear weights | adopt |
| M3 | Halving the DQ charge when DR is already mismatched | adopt |
| M4 | C weighted only when typed, never imputed from B | adopt |
| M5 | DRB3/4/5 null suffix in matching | stays REVIEW (HA-011b) |
| M6 | Which loci Iranian laboratories type, at what resolution, and how they report DQ | unknown |
| M7 | Whether two-field re-typing is possible for shortlisted pairs | unknown |
| M8 | Policy version bump to `IR-KIDNEY-MATCH-2.0.0` | after M1-M4 |

---

*Appendix A, the per-paper evidence with verbatim support, is generated from the
evidence files into `HLA_EVIDENCE_APPENDIX_2026-09-08.md`.*
