# ADR 0007 — The template registry stores RELATIONS, not cell coordinates

**Status:** ACCEPTED (2026-09-02)
**Supersedes:** `OCR_SPEC.md` §5, which specifies a template as "field bounding
boxes in normalized coordinates; locus mapping per cell".

## The measurement that forces this

Within a geometric family of 1,034 documents that is otherwise clean, the printed
**`DRB4` label occupies two different columns in the same row**, 0.285 apart in
normalized x (modal 0.58, second mode 0.42). Splitting that family on the `DRB4`
anchor yields two sub-templates that each pass every purity gate.

**But the layout signature cannot tell the two sub-templates apart.** For the 703
members that lack a readable `DRB4` anchor, the cosine similarity to the two
sub-template centroids differs by less than 0.01, and assigning them by nearest
centroid re-introduces a `DRB3` failure.

**Layout geometry provably cannot resolve the variant that decides where `DRB4`
goes.** An absolute cell rectangle authored against that family would bind the
wrong locus for roughly 40% of its members — silently, on a family that looks
perfectly coherent by every clustering statistic we have.

That is the exact failure `OCR_SPEC.md` §2 forbids, arriving through the
mechanism the spec proposed to prevent it.

## Decision

A template entry stores the **relation between a locus label and its value**, not
the coordinates of either.

```
template_registry[family_id][locus] = {
    "anchor_regex": "^(?:HLA[-\\s]?)?DRB4$",   # the printed LABEL, never a value
    "value_rule": {"dir": "right", "same_row_tol": 0.6, "max_gap": 2.5},
    "authored_by": "...", "spec_version": "...",
}
```

Per document: locate the anchor box, take the value box by the stored relation,
and emit `REVIEW_REQUIRED` when the anchor is absent, appears more than once, or
the relation is ambiguous.

This is **more** faithful to "geometry determines the locus" than absolute boxes,
not less: the geometry is re-established from the page in front of us on every
image, rather than inherited from a family average that may not apply to this
member.

## The anchor must match the LABEL, never a value prefix

`\bDRB1\b` also matches the `DRB1` inside `DRB1*11`. Measured over the 33,048
extracted documents, that inflates apparent locus presence by **5.18× for DRB1**
and **5.15× for DQB1**.

For the corpus question — *does this archive contain DQ typing?* — matching a
value token is legitimate evidence, and the finding that **DQ data is present on
about half of unique images stands**.

For template discovery it is corrupting, because it places the "locus position"
wherever a patient-specific value happened to fall rather than where the form
prints its label. Anchors are therefore matched with `^(?:HLA[-\s]?)?<LOCUS>$`
against a stripped token.

Measured anchor availability with label-only matching:

| locus | exactly one label anchor | more than one |
|---|---|---|
| DRB1 | 77.8% | 3.1% |
| DQB1 | 69.4% | 2.9% |
| DPB1 | 64.5% | 0.5% |
| DQA1 | 60.7% | 0.5% |
| DRB3 | 47.6% | **17.7%** |
| DRB4 | 30.1% | 3.6% |
| DRB5 | 16.6% | 1.0% |

`DRB3`'s 17.7% multi-occurrence rate is the combined `DRB3/4/5` header form. It
needs its own anchor type; treating it as a single-locus label would bind one
value to three genes, which §7 of `HLA_VALIDATION_SPEC.md` explicitly forbids.

## Cluster sizes overstate template prevalence by about 2×

Of 16,571 documents carrying ≥4 allele tokens, only **7,764 distinct
fingerprints** remain after near-duplicate collapse — **71.7% share a fingerprint
with another document**, and single documents recur up to 55 times inside one
cluster. Per-cluster effective-sample ratios measure 0.41–0.66.

Report families by **effective** sample size. A family of 800 documents may carry
only ~400 independent observations, and a golden-corpus allocation computed on
raw counts would over-sample the duplicated ones.

## One laboratory dominates

`YEKTA` is readable in **66.9%** of documents, and
`P(YEKTA | phone 021-6693262x) = 0.977`, `P(YEKTA | GHADR) = 0.976` — those are
one letterhead. 32% carry none of the known markers.

Geometry clusters map many-to-one onto text clusters (three geometry clusters →
one text cluster at 100%). **Text identifies the laboratory; geometry identifies
the template version within that laboratory.** Use both: the lab letterhead is a
strong, cheap prior that geometry alone does not provide.

## Consequences for what we have already built

- `scripts/template_discovery.py` used the value-matching pattern. Corrected to
  label-only; the family set changed from 5 covering 1,571 documents to **11
  covering 2,479**. The earlier figures should not be quoted.
- Its verification (independent layout coherence) is **necessary but not
  sufficient.** A stronger test is **locus anchor purity**: the fraction of
  members whose printed label falls in one modal position, plus the size of the
  largest competing mode. That test catches the `DRB4` two-column case, which
  coherence does not.
- No cell boxes should be authored for any family until the registry is
  relation-based. The golden sample remains valid — it selects documents, not
  coordinates.
