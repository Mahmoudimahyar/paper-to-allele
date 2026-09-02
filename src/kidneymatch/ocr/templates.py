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
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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


def constant_label_positions(boxes: list[Box]) -> dict[str, tuple[float, float]]:
    """Centre of each form-printed locus label, when it appears exactly once.

    Boxes on a grouped `DRB3/4/5` header's row are excluded even when they name
    a locus: there they are the patient's presence typing, and treating them as
    form furniture is what fragmented the families. A label that appears more
    than once has no single position, so it contributes nothing rather than an
    arbitrary one.
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

    seen: dict[str, list[tuple[float, float]]] = {}
    for box in boxes:
        locus = canonical_locus_label(box.text or "")
        if locus not in CONSTANT_LABELS or on_a_header_row(box):
            continue
        seen.setdefault(locus, []).append((box.centre_x, box.centre_y))
    return {locus: places[0] for locus, places in seen.items() if len(places) == 1}


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


def assign_prototype(boxes: list[Box], prototypes: list[LayoutPrototype]) -> Assignment | None:
    """Which form this document is, or None when the page does not say.

    None is a legitimate and common answer. The caller uses the default relation
    for it; claiming a family would apply that family's authored cell rule to a
    layout it was never measured on.
    """
    positions = constant_label_positions(boxes)
    scored: list[tuple[float, LayoutPrototype, SimilarityFit]] = []
    for prototype in prototypes:
        fit = fit_similarity(positions, prototype)
        if fit is not None and fit.residual <= MAX_RESIDUAL:
            scored.append((fit.residual, prototype, fit))
    if not scored:
        return None

    scored.sort(key=lambda item: item[0])
    best_residual, prototype, fit = scored[0]
    if len(scored) > 1:
        runner_up = scored[1][0]
        # A tie, or a near-tie, means the geometry does not identify the form.
        if runner_up <= max(best_residual * AMBIGUITY_MARGIN, best_residual + 1e-9):
            return None
    return Assignment(
        prototype_id=prototype.prototype_id,
        scale=fit.scale,
        residual=fit.residual,
        n_labels=fit.n_labels,
    )
