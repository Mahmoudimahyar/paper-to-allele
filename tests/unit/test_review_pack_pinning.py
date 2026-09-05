"""A refreshed pack must not orphan the answers a person already gave.

The pack's sample is stratified by what the pipeline currently says about a
document, so re-extracting the facts moves documents between strata and the
round-robin picks a different 150. Measured on 2026-09-05: after a refresh only
11 of 220 existing labels still landed on a chosen document.

Labels are the scarcest thing this project has — they are the only ground truth
it will ever have — so any document a person has answered a cell on is pinned
into the next pack, and the stratified sample fills up around it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from review_pack import choose, pinned_shas  # noqa: E402


@dataclass
class FakeDoc:
    """Only the parts of `Doc` that `choose` reads."""

    sha256: str
    rel_path: str = "photos/x.jpg"
    family: str | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def short(self) -> str:
        return self.sha256[:16]


def write_export(tmp_path: Path, cell_ids: list[str], name: str = "labels.json") -> Path:
    path = tmp_path / name
    path.write_text(
        json.dumps({"schema": "golden-labels/v1", "cells": dict.fromkeys(cell_ids, {})}),
        encoding="utf-8",
    )
    return path


def test_the_documents_behind_a_label_export_are_recovered(tmp_path: Path) -> None:
    export = write_export(tmp_path, ["a" * 16 + ":A", "a" * 16 + ":B", "b" * 16 + ":DRB1"])
    assert pinned_shas([export]) == {"a" * 16, "b" * 16}


def test_several_exports_are_unioned(tmp_path: Path) -> None:
    first = write_export(tmp_path, ["a" * 16 + ":A"], "one.json")
    second = write_export(tmp_path, ["c" * 16 + ":B"], "two.json")
    assert pinned_shas([first, second]) == {"a" * 16, "c" * 16}


def test_a_missing_or_unreadable_export_pins_nothing(tmp_path: Path) -> None:
    """A typo in a path must not silently drop a labeller's work."""
    assert pinned_shas([tmp_path / "absent.json"]) == set()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert pinned_shas([broken]) == set()


def test_a_cell_id_that_is_not_a_document_id_is_ignored(tmp_path: Path) -> None:
    export = write_export(tmp_path, ["short:A", ":B", "a" * 16 + ":C"])
    assert pinned_shas([export]) == {"a" * 16}


def test_a_pinned_document_is_chosen_however_the_strata_move(tmp_path: Path, monkeypatch) -> None:
    """The whole point: the pinned document survives a change of stratum."""
    import review_pack

    docs = {f"{i:064x}": FakeDoc(f"{i:064x}") for i in range(1, 60)}
    monkeypatch.setattr(review_pack, "tag_document", lambda doc, export: ["clean_control"])
    monkeypatch.setattr(Path, "exists", lambda self: True)
    pinned = f"{57:064x}"[:16]

    chosen = choose(docs, n=5, seed=1, export=tmp_path, pin={pinned})
    assert pinned in {d.short for d in chosen}
    assert len(chosen) == 5


def test_pinning_does_not_grow_the_pack_beyond_n(tmp_path: Path, monkeypatch) -> None:
    """A pinned document takes a place in the sample; it does not add one."""
    import review_pack

    docs = {f"{i:064x}": FakeDoc(f"{i:064x}") for i in range(1, 60)}
    monkeypatch.setattr(review_pack, "tag_document", lambda doc, export: ["clean_control"])
    monkeypatch.setattr(Path, "exists", lambda self: True)
    pins = {f"{i:064x}"[:16] for i in range(1, 4)}

    chosen = choose(docs, n=5, seed=1, export=tmp_path, pin=pins)
    assert len(chosen) == 5
    assert pins <= {d.short for d in chosen}


def test_no_pin_leaves_the_sample_as_it_was(tmp_path: Path, monkeypatch) -> None:
    import review_pack

    docs = {f"{i:064x}": FakeDoc(f"{i:064x}") for i in range(1, 60)}
    monkeypatch.setattr(review_pack, "tag_document", lambda doc, export: ["clean_control"])
    monkeypatch.setattr(Path, "exists", lambda self: True)

    assert [d.short for d in choose(docs, 5, 1, tmp_path)] == [
        d.short for d in choose(docs, 5, 1, tmp_path, pin=set())
    ]
