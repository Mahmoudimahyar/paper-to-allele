"""Recognise which printed form a document is, from its label geometry.

Template discovery assigned **707 of 23,485** documents to a verified family
while one laboratory alone accounts for about two thirds of the corpus. The
skeptical review of ADR 0008 diagnosed three causes, all reproduced:

1. **The signature counted the grouped row's VALUES as labels.** 12,178 of
   12,641 standalone `DRB3` boxes sit on the `DRB3/4/5` header's row, where they
   are the patient's presence typing rather than form furniture. One form
   therefore split into at least seven "templates" by genotype, and 4,262
   documents fell into groups too small to cluster and were discarded. It also
   explains ADR 0007's `DRB4` "in two columns 0.285 apart": `DRB4` sits at
   x 0.709 when `DRB3` shares its row and 0.474 when it is alone. That was never
   two sub-templates — it was one row with a variable number of values.
2. **Absolute page coordinates on hand-held photographs.** The `HLA-A` label
   spans y 0.165 to 0.408 between the 10th and 90th percentiles, so clustering
   in page space fragments one form into position blobs and leaves 4,195 of
   7,299 fully-labelled documents as noise.
3. Anchor purity then failed on those value-bearing "labels".

The fix is in this module: build the signature only from labels the FORM prints
in a fixed place, and compare documents by fitting a similarity transform rather
than by page coordinates. Measured, that raises coverage to **14,876 documents
(63.3%)** with no ambiguous assignments.

**An unassigned document is not a failure.** It gets the default relation. What
must never happen is claiming a family a page does not belong to, because that
applies the family's authored cell rule to a layout it was never measured on.

## One repair and two accommodations, in the order they are tried

11,210 documents still carry no family, and two thirds of the reason is not
that the page is a different form. `assign_prototype` asks three questions,
and the order is the point: the ordinary fit first, then the REPAIR, and only
what is left over reaches the accommodation.

1. **A near-tie between prototypes of ONE form.** Measured on this build over
   the 11,198 no-family pages that still hold an unread cell: 983 fit inside
   `MAX_RESIDUAL` and were refused only because a second prototype fitted
   nearly as well, and 965 of those go on to read a cell — and the prototypes
   that tie are the same printed form
   photographed at different leans. `assign_prototype` assigns those, but only
   when the caller says the tied prototypes author one cell rule AND their rows
   agree under a y-only fit. It is not "the closest one wins": two genuinely
   different layouts still refuse each other.
2. **A label whose `HLA-` prefix the recognizer boxed apart.** That fragment
   carries the label's printed left edge away and drags its centre right,
   which is what pushes the page's stack past the tolerance. The fragment is
   ON THE PAGE, so it is put back (`merge_prefix_fragments`) and the ORDINARY
   question is asked again at the ORDINARY tolerance. Measured on this build:
   206 of the 11,198 assign this way and 162 of them read a cell the repass can
   write (+267 in a re-extraction, per
   `.artifacts/no-family/extraction-diff-vs-pre-change.log`), and the 2,000
   already-assigned pages sampled there are untouched — the merge is tried only
   after the plain fit has refused. The repaired boxes are also what the page is
   then READ from, or the same displacement hands the label's value to the next
   locus down.
3. **A stack that fits except at ONE label, with no fragment to explain it.**
   The residue: 212 pages assign this way on this build and 209 read a cell
   (+259 in a re-extraction). The left-out fit admits them at half
   the tolerance. It is not a perspective correction — the dropped label is a
   MIDDLE label on most of them — and it is not a licence to drop an
   inconvenient point: the dropped box must still stand in the page's label
   column and its deviation must be in x. Its placebo is a prototype
   translated by one row, which a uniformly-pitched stack fits perfectly once
   the wrapped label is dropped; the x-dominance test is what refuses it.

Measured against the pre-change build, doing the repair FIRST rather than
accommodating everything gains 161 cells over the left-out fit alone and
assigns 108 more pages. What it does NOT do is repair the left-out fit's own
losses: of the 34 cells that fit lost to review, the merge repairs 0 and adds
4, because on those pages the displaced label has no `HLA-` box to put back.

All three are for READING a page, never evidence for building a form, so
`template_discovery.py` gets none of them.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from statistics import median
from types import MappingProxyType

from kidneymatch.ocr.anchors import Box
from kidneymatch.ocr.drbx import find_grouped_headers
from kidneymatch.ocr.glyphs import canonical_locus_label

# Labels the form itself prints, in a place that does not depend on the patient.
# DRB3, DRB4 and DRB5 are deliberately absent: on this corpus they are almost
# always the grouped row's values.
CONSTANT_LABELS: tuple[str, ...] = ("A", "B", "C", "DRB1", "DQA1", "DQB1", "DPA1", "DPB1")

# Fewer than three correspondences cannot test a scale-and-offset fit: two
# points determine one exactly, so any pair "fits" any prototype.
MIN_LABELS = 3

# Residual as a FRACTION of the prototype's own extent, so the threshold means
# the same thing however the prototype was built. An absolute page-unit
# threshold is meaningless here: a prototype's coordinates carry whatever scale
# the documents it was built from happened to have. Measured on the real corpus
# in the normalised frame, a true fit has p50 0.0035, p90 0.020, p99 0.037.
MAX_RESIDUAL = 0.04

# A second prototype fitting nearly as well means the page does not identify its
# form; both would author a different cell rule for the same cells.
AMBIGUITY_MARGIN = 1.5

# ...unless the prototypes that tie are ONE FORM. Measured over the 11,210
# pages with no family: 987 fit inside MAX_RESIDUAL and were refused only for a
# near-tie, and on every one of them the tied prototypes are FORM#0/#1/#3 —
# the same printed form leaning three ways. Three measurements say so and the
# tie clause below encodes the third:
#
# * the y-only residual, which is the row ORDER and PITCH with the lean taken
#   out, is 0.008 at p50 and 0.023 at p99 on the tie pages against 0.003 and
#   0.023 on uniquely-assigned ones, while a mid-band decoy reaches 0.04 on
#   10% of pages and a genuinely different form on 94%;
# * the leans of the tied prototypes bracket the page's own;
# * forcing the runner-up instead of the best changes ONE cell of 7,896.
#
# So a tie is not ambiguity when the tied prototypes author the same cell rule
# AND agree on which row each label is printed on. Rule-id equality alone is
# not enough: the virtual-anchor path in `extract_facts.bind_in_lattice` places
# an unreadable label where the prototype says it is printed, and a prototype
# with a different row order would place it on the wrong row.
#
# Deliberately the same number as the 2-D gate. It is a different question —
# one dimension, prototype against prototype — and answering it at the same
# tolerance is what makes "these are one form" mean no more than "this page is
# that form" already does.
LEAN_MAX_RESIDUAL = MAX_RESIDUAL

# A page whose printed stack fits a form except at ONE label.
#
# What the rule REACHES, measured on this build read-only against the live
# stores (`family_repass.py --dry-run`, 2026-09-07): 209 pages, because the
# `HLA-` repair below is tried first and takes 162 pages at the ordinary
# tolerance. With the repair disabled the same pass assigns 263 pages by this
# fit, so the repair removes 54 of them and the rest of its 162 were refused
# outright.
#
# The tolerance and the two conditions below were CALIBRATED on the earlier
# survey of 1,405 refused >= 6-label pages, before the repair was tried first:
# 318 of them fitted within 0.02 with one label left out, on 310 the dropped
# label's deviation under the full fit was in x — the recognizer boxed its
# `HLA-` prefix separately (138) or did not box the prefix at all (103) —
# and the dropped label was a MIDDLE label of the stack on 241, so this is not
# perspective and not the end of the stack. Those are the survey's figures and
# not this build's; what this build produces is the 209 above.
#
# Half the plain tolerance, because a point was removed: five remaining labels
# fitted at 0.04 is a weaker claim than eight fitted at 0.04.
LOO_MAX_RESIDUAL = 0.02
# ...and never on fewer, because fitting four remaining points is the weakest
# case there is (it costs 82 pages against a five-label gate).
LOO_MIN_LABELS = 6
# The dropped label's box must still stand in the page's own label column. On
# the calibration survey's 318 it sits a median 3.3 label heights right of it
# (p90 23); on the 44 pages the rule would otherwise admit it sits a median 26
# heights right, which is the VALUE area — there the dropped box is a value the
# recognizer read as a bare locus name, not a label whose prefix was boxed
# apart. Survey figures: this gate has not been re-swept since the repair
# started running first.
LABEL_COLUMN_HEIGHTS = 6.0

# The `HLA-` a recognizer boxes apart from the label it belongs to. This is the
# CAUSE of the left-out fit's population — the fragment carries the label's
# printed left edge away and drags its centre right — so where the fragment is
# on the page it can be put back instead of accommodated, and the label's box
# is then the one the form printed. Nothing here reads a locus from text: the
# fragment names no gene, and the box it is joined to already named one.
PREFIX_FRAGMENT = re.compile(r"^H\s*[L1I]\s*[A4]\s*[-–—:.]?$", re.IGNORECASE)
# How far the fragment's right edge may sit from the label's left edge, in
# label heights, and how far off its line. A prefix boxed apart is touching:
# the two halves of one printed word.
FRAGMENT_MAX_GAP = 1.0
FRAGMENT_MAX_OFFSET = 0.6


@dataclass(frozen=True, slots=True)
class SimilarityFit:
    """A scale and offset carrying one document's labels onto a prototype's."""

    scale: float
    dx: float
    dy: float
    residual: float
    n_labels: int


@dataclass(frozen=True, slots=True)
class LayoutPrototype:
    """One printed form, as the positions of the labels it always prints."""

    prototype_id: str
    positions: MappingProxyType[str, tuple[float, float]]

    @classmethod
    def from_positions(
        cls, prototype_id: str, positions: dict[str, tuple[float, float]]
    ) -> LayoutPrototype:
        return cls(prototype_id, MappingProxyType(dict(positions)))


@dataclass(frozen=True, slots=True)
class Assignment:
    """Which form a document is, and the evidence for saying so."""

    prototype_id: str
    scale: float
    residual: float
    n_labels: int
    # Prototypes that fitted within `AMBIGUITY_MARGIN` of this one and were
    # judged the same form under lean. Empty on a page that names its form
    # outright; a caller that publishes the assignment should say so.
    tied_with: tuple[str, ...] = ()
    # The label left out to make this fit, when the page's stack fits except at
    # one label. `None` for a plain fit. A caller must NOT place a virtual
    # anchor for this label: its printed position is the one the page
    # contradicted.
    dropped_label: str | None = None
    # Loci whose `HLA-` prefix was boxed apart and put back before this fit was
    # tried. Non-empty means the page fitted the form once its labels were the
    # words the form prints, which is a repair rather than an accommodation —
    # and a caller that reads the page should read it from the repaired boxes,
    # or the same displacement that broke the fit will hand the label's value
    # to the next locus down.
    merged_prefixes: tuple[str, ...] = ()
    # The best residual of any OTHER prototype, so the margin the assignment
    # won by is visible in provenance rather than only inside this function.
    runner_up_residual: float | None = None


def constant_label_boxes(boxes: list[Box]) -> dict[str, Box]:
    """The box of each form-printed locus label, when it appears exactly once.

    `constant_label_positions` is this, reduced to centres. The boxes are kept
    because the left-out fit has to ask where the dropped label's box SAT — a
    label whose printed prefix was boxed apart still stands in the label
    column, and a value the recognizer read as a bare locus name does not.
    """
    header_rows = [(header.y0, header.y1, header.x1) for header in find_grouped_headers(boxes)]

    def on_a_header_row(box: Box) -> bool:
        for y0, y1, x1 in header_rows:
            if box.x0 <= x1:
                continue
            overlap = min(y1, box.y1) - max(y0, box.y0)
            if overlap > 0:
                return True
        return False

    seen: dict[str, list[Box]] = {}
    for box in boxes:
        locus = canonical_locus_label(box.text or "")
        if locus not in CONSTANT_LABELS or on_a_header_row(box):
            continue
        seen.setdefault(locus, []).append(box)
    return {locus: found[0] for locus, found in seen.items() if len(found) == 1}


def merge_prefix_fragments(
    boxes: list[Box],
) -> tuple[list[Box], tuple[str, ...], dict[int, tuple[Box, Box]]]:
    """Put back each `HLA-` the recognizer boxed apart from the label it prefixes.

    Returns the boxes with every such pair joined into the word the form
    actually prints, the loci that were repaired, and, for each joined box, the
    two boxes it was made of — so a caller holding a map back to the page as
    STORED can extend it rather than reporting a box in the levelled frame.
    The joined box keeps the LABEL's text, not the fragment's: geometry is what
    changes here, and the locus a box names must go on coming from the same
    characters it came from before.

    This is the direct repair of what the left-out fit accommodates. A label
    whose prefix is boxed apart has its centre dragged right by half the
    prefix, which is what pushes the page's stack past the template tolerance
    — and the same displacement is what hands the label's own value to the
    NEXT locus's label under the ownership gate. Joining the two boxes fixes
    both; leaving the label out of the fit fixes only the first.
    """
    fragments = [box for box in boxes if PREFIX_FRAGMENT.match((box.text or "").strip())]
    if not fragments:
        return boxes, (), {}
    joined: dict[int, Box] = {}
    sources: dict[int, tuple[Box, Box]] = {}
    consumed: set[int] = set()
    repaired: list[str] = []
    for box in boxes:
        locus = canonical_locus_label(box.text or "")
        if locus is None:
            continue
        for fragment in fragments:
            if id(fragment) in consumed:
                continue
            gap = box.x0 - fragment.x1
            if not -1e-9 <= gap <= FRAGMENT_MAX_GAP * box.height:
                continue
            if abs(fragment.centre_y - box.centre_y) > FRAGMENT_MAX_OFFSET * box.height:
                continue
            consumed.add(id(fragment))
            merged = Box(
                min(box.x0, fragment.x0),
                min(box.y0, fragment.y0),
                max(box.x1, fragment.x1),
                max(box.y1, fragment.y1),
                box.text,
            )
            joined[id(box)] = merged
            sources[id(merged)] = (box, fragment)
            repaired.append(locus)
            break
    if not joined:
        return boxes, (), {}
    out = [joined.get(id(box), box) for box in boxes if id(box) not in consumed]
    return out, tuple(sorted(set(repaired))), sources


def constant_label_positions(boxes: list[Box]) -> dict[str, tuple[float, float]]:
    """Centre of each form-printed locus label, when it appears exactly once.

    Boxes on a grouped `DRB3/4/5` header's row are excluded even when they name
    a locus: there they are the patient's presence typing, and treating them as
    form furniture is what fragmented the families. A label that appears more
    than once has no single position, so it contributes nothing rather than an
    arbitrary one.
    """
    return {
        locus: (box.centre_x, box.centre_y) for locus, box in constant_label_boxes(boxes).items()
    }


def fit_y_only(
    source: Mapping[str, tuple[float, float]], target: Mapping[str, tuple[float, float]]
) -> float | None:
    """Residual of the best scale-and-offset in y alone, carrying one set of
    label positions onto another.

    The same normalisation as `fit_similarity`: a fraction of how far the
    TARGET's labels spread, so the number means the same thing whatever
    coordinates either side uses. What it asks is narrower — do these two
    layouts print the same rows in the same order at the same pitch? — and
    that is exactly the question a lean must not be allowed to answer. `None`
    when too few labels are shared to test anything.
    """
    shared = sorted(set(source) & set(target))
    if len(shared) < MIN_LABELS:
        return None
    ys = [source[label][1] for label in shared]
    yt = [target[label][1] for label in shared]
    n = len(shared)
    mean_source = sum(ys) / n
    mean_target = sum(yt) / n
    denominator = sum((y - mean_source) ** 2 for y in ys)
    spread = math.sqrt(sum((y - mean_target) ** 2 for y in yt) / n)
    if denominator <= 1e-12 or spread <= 1e-12:
        return None
    scale = sum((a - mean_source) * (b - mean_target) for a, b in zip(ys, yt, strict=True))
    scale /= denominator
    if scale <= 0:
        return None  # the rows in the opposite order is not the same form
    offset = mean_target - scale * mean_source
    error = math.sqrt(sum((scale * a + offset - b) ** 2 for a, b in zip(ys, yt, strict=True)) / n)
    return error / spread


def fit_similarity(
    positions: dict[str, tuple[float, float]], prototype: LayoutPrototype
) -> SimilarityFit | None:
    """Best isotropic scale and offset carrying `positions` onto the prototype.

    Isotropic and rotation-free on purpose: these are photographs of a page held
    roughly square, so scale and offset absorb the variation while a rotation
    term would let genuinely different layouts fit.
    """
    shared = sorted(set(positions) & set(prototype.positions))
    if len(shared) < MIN_LABELS:
        return None

    source = [positions[label] for label in shared]
    target = [prototype.positions[label] for label in shared]
    n = len(shared)
    mean_source = (sum(p[0] for p in source) / n, sum(p[1] for p in source) / n)
    mean_target = (sum(q[0] for q in target) / n, sum(q[1] for q in target) / n)

    numerator = sum(
        (p[0] - mean_source[0]) * (q[0] - mean_target[0])
        + (p[1] - mean_source[1]) * (q[1] - mean_target[1])
        for p, q in zip(source, target, strict=True)
    )
    denominator = sum((p[0] - mean_source[0]) ** 2 + (p[1] - mean_source[1]) ** 2 for p in source)
    if denominator <= 1e-12:
        return None  # every label at one point: no scale is determined
    scale = numerator / denominator
    if scale <= 0:
        return None  # a mirrored or degenerate fit is not this form

    dx = mean_target[0] - scale * mean_source[0]
    dy = mean_target[1] - scale * mean_source[1]
    error = math.sqrt(
        sum(
            (scale * p[0] + dx - q[0]) ** 2 + (scale * p[1] + dy - q[1]) ** 2
            for p, q in zip(source, target, strict=True)
        )
        / n
    )
    # Expressed as a fraction of how far the prototype's labels spread, so the
    # same misfit is judged the same way whatever coordinates the prototype uses.
    spread = math.sqrt(
        sum((q[0] - mean_target[0]) ** 2 + (q[1] - mean_target[1]) ** 2 for q in target) / n
    )
    if spread <= 1e-12:
        return None
    return SimilarityFit(scale=scale, dx=dx, dy=dy, residual=error / spread, n_labels=n)


def _collinear(points: list[tuple[float, float]]) -> bool:
    """Do these label centres stand in one line, to within the fit's tolerance?

    Points in a line carry no evidence about a two-column layout: any scale and
    offset that matches their pitch matches them, whatever the second column
    does. Measured, that is how a five-label two-column prototype beat an
    eight-point fit on the A/B/C triple alone.
    """
    n = len(points)
    if n < MIN_LABELS:
        return True
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mean_x) ** 2 for p in points) / n
    syy = sum((p[1] - mean_y) ** 2 for p in points) / n
    sxy = sum((p[0] - mean_x) * (p[1] - mean_y) for p in points) / n
    spread = sxx + syy
    if spread <= 1e-12:
        return True
    # The smaller eigenvalue of the 2x2 scatter matrix is the mean square
    # distance from the line the points best lie on.
    smaller = (spread - math.sqrt((sxx - syy) ** 2 + 4 * sxy**2)) / 2
    return math.sqrt(max(smaller, 0.0)) <= MAX_RESIDUAL * math.sqrt(spread)


def _admissible(
    positions: dict[str, tuple[float, float]],
    prototype: LayoutPrototype,
    prototypes: list[LayoutPrototype],
) -> bool:
    """May this prototype compete for a page printing these labels?

    Two gates, both from the same measured failure. A five-label form was
    induced from its own pages and, fitted in the ordinary way, took 18 pages
    that print `DPA1`, `DPB1` or `DQA1` — labels it does not have — and 66 to
    103 pages away from the eight-label family they belonged to, on the
    strength of a three-label collinear fit. 165 already-resolved cells were
    lost that way.

    * A page printing a constant label the prototype LACKS cannot be that
      form. The fit never sees the extra label, so nothing else says so.
    * A prototype whose labels are a strict subset of another's competes only
      when the page shows enough of them to tell the two forms apart — which
      means its printed labels must not stand in a single line.
    """
    if set(positions) - set(prototype.positions):
        return False
    subset = any(
        set(prototype.positions) < set(other.positions)
        for other in prototypes
        if other is not prototype
    )
    if not subset:
        return True
    return not _collinear([positions[label] for label in sorted(set(positions))])


def _one_form_under_lean(
    best: LayoutPrototype,
    tied: list[LayoutPrototype],
    rule_of: Mapping[str, str] | None,
) -> bool:
    """Do the prototypes that tied author one rule and print one row order?

    Without a rule map — `template_discovery.py` builds the forms with no rule
    authored yet — a tie is always ambiguity and this says no.
    """
    if rule_of is None:
        return False
    ours = rule_of.get(best.prototype_id)
    if ours is None:
        return False
    for other in tied:
        if rule_of.get(other.prototype_id) != ours:
            return False
        residual = fit_y_only(other.positions, best.positions)
        if residual is None or residual > LEAN_MAX_RESIDUAL:
            return False
    return True


def _left_out_fit(
    label_boxes: dict[str, Box],
    positions: dict[str, tuple[float, float]],
    prototype: LayoutPrototype,
    dropped: str,
) -> bool:
    """Is the dropped label one the recognizer mis-boxed, on this prototype?

    Two conditions, both calibrated on the 318-page survey that authored this
    rule — not on what it admits today, which is the 209-page residue left once
    `merge_prefix_fragments` has run first. The box must still stand in the
    page's own label column — a box out in the value area is a VALUE read as a
    bare locus name, which is a different page and a different question — and
    its deviation under the FULL fit must be in x, because that is what boxing
    a label's `HLA-` prefix apart does to its centre. A label off in y is a
    different row order.
    """
    box = label_boxes.get(dropped)
    full = fit_similarity(positions, prototype)
    if box is None or full is None:
        return False
    heights = [b.height for b in label_boxes.values()]
    left_edges = [b.x0 for b in label_boxes.values()]
    if not heights:
        return False
    if box.x0 - median(left_edges) > LABEL_COLUMN_HEIGHTS * median(heights):
        return False
    px, py = positions[dropped]
    qx, qy = prototype.positions[dropped]
    dx = full.scale * px + full.dx - qx
    dy = full.scale * py + full.dy - qy
    return abs(dx) >= abs(dy)


def assign_prototype(
    boxes: list[Box],
    prototypes: list[LayoutPrototype],
    rule_of: Mapping[str, str] | None = None,
    leave_one_out: bool = False,
) -> Assignment | None:
    """Which form this document is, or None when the page does not say.

    None is a legitimate and common answer. The caller uses the default relation
    for it; claiming a family would apply that family's authored cell rule to a
    layout it was never measured on.

    `rule_of` maps a prototype id to the id of the cell rule it authors. Given
    it, a near-tie between prototypes that author ONE rule and agree on the row
    order is assigned rather than refused, and the tie is recorded on the
    assignment. Without it every near-tie is still refused.

    `leave_one_out` admits a page whose stack fits except at one label, at half
    the plain tolerance. It is off by default because a prototype must not be
    BUILT from a page one of whose labels contradicts it: this is an
    accommodation for reading, not evidence of a form.
    """

    def plain(
        positions: dict[str, tuple[float, float]], merged: tuple[str, ...]
    ) -> Assignment | None:
        """The ordinary fit, at the full tolerance, over these label positions."""
        admissible = [p for p in prototypes if _admissible(positions, p, prototypes)]
        scored: list[tuple[float, LayoutPrototype, SimilarityFit]] = []
        for prototype in admissible:
            fit = fit_similarity(positions, prototype)
            if fit is not None and fit.residual <= MAX_RESIDUAL:
                scored.append((fit.residual, prototype, fit))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0])
        best_residual, prototype, fit = scored[0]
        margin = max(best_residual * AMBIGUITY_MARGIN, best_residual + 1e-9)
        tied = [other for residual, other, _ in scored[1:] if residual <= margin]
        if tied and not _one_form_under_lean(prototype, tied, rule_of):
            # A tie, or a near-tie, between different forms means the geometry
            # does not identify this one.
            return None
        return Assignment(
            prototype_id=prototype.prototype_id,
            scale=fit.scale,
            residual=fit.residual,
            n_labels=fit.n_labels,
            tied_with=tuple(other.prototype_id for other in tied),
            runner_up_residual=scored[1][0] if len(scored) > 1 else None,
            merged_prefixes=merged,
        )

    label_boxes = constant_label_boxes(boxes)
    positions = {locus: (box.centre_x, box.centre_y) for locus, box in label_boxes.items()}
    assignment = plain(positions, ())
    if assignment is not None:
        return assignment

    if not leave_one_out:
        return None

    # The plain fit refused. Before accommodating the page, REPAIR it: a label
    # whose `HLA-` prefix the recognizer boxed apart is not a label in the
    # wrong place, it is half a label, and the other half is on the page. Put
    # it back and ask the ordinary question again, at the ordinary tolerance.
    # Only then is what remains the residue the left-out fit is for.
    merged_boxes, merged, _ = merge_prefix_fragments(boxes)
    if merged:
        merged_label_boxes = constant_label_boxes(merged_boxes)
        merged_positions = {
            locus: (box.centre_x, box.centre_y) for locus, box in merged_label_boxes.items()
        }
        assignment = plain(merged_positions, merged)
        if assignment is not None:
            return assignment
        # The left-out fit, too, asks about the page whose labels are whole.
        label_boxes, positions = merged_label_boxes, merged_positions

    if len(positions) < LOO_MIN_LABELS:
        return None
    admissible = [p for p in prototypes if _admissible(positions, p, prototypes)]

    # The residue. Try the fit once more with each printed label left out, at
    # half the tolerance, and only where the dropped label looks like one the
    # recognizer mis-boxed rather than a row this form does not have.
    left_out: list[tuple[float, LayoutPrototype, SimilarityFit, str, float | None]] = []
    for dropped in sorted(positions):
        kept = {locus: point for locus, point in positions.items() if locus != dropped}
        fits = []
        for prototype in admissible:
            fit = fit_similarity(kept, prototype)
            if fit is not None:
                fits.append((fit.residual, prototype, fit))
        if not fits:
            continue
        fits.sort(key=lambda item: item[0])
        residual, prototype, fit = fits[0]
        runner_up = fits[1][0] if len(fits) > 1 else None
        if residual > LOO_MAX_RESIDUAL:
            continue
        if not _left_out_fit(label_boxes, positions, prototype, dropped):
            continue
        # The mainline ambiguity margin, on the left-out fit. A second
        # prototype fitting the same reduced stack as well means the page has
        # said even less than usual about which form it is.
        if runner_up is not None and runner_up <= max(residual * AMBIGUITY_MARGIN, residual + 1e-9):
            continue
        left_out.append((residual, prototype, fit, dropped, runner_up))

    if not left_out:
        return None
    left_out.sort(key=lambda item: item[0])
    residual, prototype, fit, dropped, runner_up = left_out[0]
    return Assignment(
        prototype_id=prototype.prototype_id,
        scale=fit.scale,
        residual=fit.residual,
        n_labels=fit.n_labels,
        dropped_label=dropped,
        runner_up_residual=runner_up,
        merged_prefixes=merged,
    )
