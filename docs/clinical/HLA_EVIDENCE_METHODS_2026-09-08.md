# Methods: evidence review of HLA matching in kidney transplantation

Companion to `HLA_MATCHING_EVIDENCE_V2_2026-09-08.md`. This document records the
protocol so the review can be audited and repeated.

## 1. Question

In living-donor kidney transplantation, using antigen-level (one-field) typing
and with no antibody or crossmatch data available:

1. Which HLA loci carry weight, and in what order?
2. Is the penalty for additional mismatches constant (an additive score), or
   does it have another shape?
3. How much should a second mismatch at a locus weigh relative to the first?
4. Which other factors modify the HLA effect enough to belong in the model?

## 2. Information sources and dates

- **PubMed / PubMed Central**, through an MCP connector exposing E-utilities
  search, article metadata, identifier conversion and PMC full text.
- **Consensus** (indexes Semantic Scholar, PubMed, Scopus and arXiv), used for
  conference abstracts that PubMed does not index. The account permits 30
  searches per month; the quota was exhausted during the discovery stage, so
  extraction and verification used PubMed and PMC only. This is recorded as a
  limitation, not worked around.

Searches ran on **7–8 September 2026**.

## 3. Search strategy

Eight independent search strands ran in parallel, each with its own agent and
its own query set, covering:

| Strand | Focus | PubMed queries |
|---|---|---|
| A | Shape of the total-mismatch dose-response; zero-mismatch premium | 35 |
| B | Per-locus estimates separating one from two mismatches | 36 |
| C | Locus interactions, non-additive scoring, matchability | 35 |
| D | Effect modification (sensitisation, age, donor type, ischaemia, ethnicity, immunosuppression, retransplant) | 22 |
| E | Molecular mismatch and non-linearity (eplet, PIRCHE-II, electrostatic, amino acid) | 17 |
| F | Allocation and living-donor selection algorithms | 33 |
| G | Iran and the wider region | 28 |
| H | Statistical and machine-learning models with HLA as a predictor | 32 |
| | **Total** | **238** |

Eight Consensus queries ran before the quota was exhausted.

Queries combined controlled vocabulary with author-anchored and phrase-anchored
forms (for example `Williams RC[Author] AND HLA AND mismatch AND kidney AND
graft survival`, `"zero HLA mismatch" AND kidney transplantation AND graft
survival`, `"number of HLA mismatches" AND kidney transplantation AND registry`).
Every candidate's existence was confirmed by retrieving its PubMed record; no
paper was listed from memory.

Ninety-two candidates were returned (69 rated core by the search agents) and
merged with a seed list of 52 papers from the previous review, giving 100 papers
after de-duplication and scope screening.

## 4. Eligibility

**Included:** kidney transplantation (kidney-alone), reporting HLA antigen or
molecular mismatch as an exposure, or reporting how another factor modifies that
effect, or describing the HLA component of an allocation or donor-selection
algorithm.

**Excluded:** pancreas-kidney, liver, heart, lung and haematopoietic
transplantation; papers where HLA appears only as a covariate with no reported
estimate; reviews, except where cited for a policy statement or for a figure
traceable to a named primary source.

**Labelled, not excluded:** congress abstracts. They are marked as such wherever
used and are never the sole support for a conclusion.

## 5. Data extraction

One agent per paper, working from PMC full text where it exists and from the
abstract otherwise, completed a fixed contract:

- bibliographic record, access route and licence;
- scope check: organ, donor type, sample size, design, typing resolution,
  outcome definition, follow-up, and which non-HLA factors were modelled;
- a written argument for why the paper's population and design do or do not
  transfer to a living-donor, one-field-typing, antibody-unknown pre-screen;
- every effect size for HLA mismatch, with confidence interval, p value,
  adjustment set and location in the paper;
- the dose-response series exactly as printed, with explicit fields for whether
  one and two mismatches were pooled and whether linearity was tested;
- every interaction or effect-modification result;
- three to six verbatim quotes of at most 40 words, each tied to one of fifteen
  numbered claims (C1–C15) and each carrying its location;
- limitations.

Numbers not present in the retrieved text were recorded as absent. Confidence
intervals and p values were never inferred.

## 6. Verification

Verification is **deterministic, not agent-based**. Each extracting agent cached
the source text it worked from, and a script (`verify_quotes.py`) then re-matched
every quote against that cached text independently of the agent's own claim.

The comparison folds only typographic variation: Unicode dash variants
(publisher XML uses the non-breaking hyphen U+2010 inside "HLA-DR"), curly
quotation marks, non-breaking and thin spaces, and a stray space before
punctuation. Punctuation itself is preserved. The normaliser is unit-tested to
confirm that it folds `HLA A , 16%` to `HLA A, 16%`, that it still distinguishes
16% from 17%, and that a paraphrase does not match. A quote differing by one
word fails; a quote over 40 words fails.

Quotes that fail are marked unverified, withheld from the appendix, and counted
in the paper's record.

This replaced a planned second-agent refutation pass, for two reasons. Agent
verifiers were the first work killed when usage limits were reached, so coverage
would have been partial and arbitrary. And the script is more complete: it
checked every quote in every paper in under a second.

**What it caught.** Of 573 quotes across 100 included papers, 550 were re-matched
successfully, 20 could not be re-matched because no source text had been cached
for their paper (flagged as lower-confidence in the appendix), and 3 failed. All
three failures came from a single paper for which PubMed Central returns an
*empty* full text; the extracting agent had disclosed that it read the table
from the publisher's web page instead. Those quotes match no retrievable source,
so they are withheld and that paper's numbers are excluded from every
quantitative claim in the review, though the agent recorded an internal
arithmetic check that they pass. This is recorded as a limitation of
verifiability, not as a finding that the paper is wrong.

Four further papers were excluded outright: three failed the kidney-only or
HLA-exposure scope test, and one Iranian cohort could not be retrieved from
PubMed or PubMed Central at all, so the extracting agent recorded it as
`not_found` and refused to cite second-hand figures for it.

The script does not check that a number was attributed to the right comparison.
The numbers used in the review's main text were therefore also re-read from the
source text by the reviewer, and each is quoted with its location.

## 7. Synthesis

Claims C1–C15 were graded on the number, size and design of supporting studies
and the consistency of their direction.

The dose-response shape was analysed by taking every published series of hazard
ratios by mismatch count and asking whether it is consistent with the log-linear
model that an additive point score implies. Two quantities were computed:

- the **multiplicative extrapolation error**, HR(1)⁶ compared with the observed
  HR(6), which measures how badly a constant per-mismatch weight misstates a
  poorly matched donor;
- the **step at zero**, the fitted intercept minus 1.00, expressed in units of
  the fitted slope.

Per locus, for every study reporting one-versus-zero and two-versus-zero
estimates in one model, the ratio of the second mismatch's log-effect to the
first's was computed as *r* = [log E(2) − log E(1)] / log E(1). Ratios where
E(1) < 1.05 were excluded as numerically unstable, since the denominator
approaches zero.

Scripts: `shape_analysis.py`, `locus_shape.py`, `dose_shape.py`,
`aggregate_evidence.py` (session scratchpad; the numbers they produce are
reproduced in the review with their sources).

## 8. Limitations of the method

- Registry studies dominate, and almost all use antigen-level typing, so the
  molecular literature answers a different question from the one the archive
  can pose.
- No Iranian outcome cohort of adequate size models HLA mismatch, so the
  transfer of every estimate to the target population rests on argument rather
  than local data.
- The published dose-response lines were fitted by the original authors to Cox
  point estimates by ordinary least squares, not by a within-model trend test or
  spline. The concavity reported here follows from their published fits and from
  the published category hazard ratios; it is not a re-analysis of patient data,
  which is not available.
- Automated extraction can mis-attribute a number to the wrong comparison. The
  verification pass catches non-verbatim quotes and numbers absent from the
  source, but not every mis-attribution; the numbers used in the review's main
  text were re-read from the source text by the reviewer.
- The Consensus quota was exhausted, so conference abstracts could not be
  re-verified mechanically. They are labelled and are never sole support.
