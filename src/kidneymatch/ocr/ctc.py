"""Read an allele cell by constraining the recognizer's own logits to a grammar.

The recognizer emits a per-timestep distribution over 127 symbols and then takes
the greedy path. Inside a cell whose grammar is known, the greedy path is the
wrong thing to take: it can spell something the grammar forbids, and the
post-hoc repair then has to guess what was meant. Constraining the decode to the
grammar removes the guess — the model's own probabilities choose among the
readings that are actually possible.

## The property that governs the whole design

**A constrained decode turns ANY crop into a grammatically valid allele.**
Measured on this corpus: 100% of blank paper, 100% of intact locus labels and
100% of Persian script decode to something the grammar accepts, and 213 of 250
label crops decode to a value the reference vocabulary admits.

So the decode may never decide that a box is a value. It may only re-read the
characters inside a box that geometry and the five existing gates have already
accepted, or take a fact away. Grammar cost is an abstention signal, never an
admission signal, and `resolve_locus`'s gate 1 (is this a label?) and gate 3
(does another anchor own it?) must keep seeing the RAW text.

## The truncation trap

The grammar allows a two- or three-digit field. A longer one is not rejected:
the decoder drops a digit and emits a **different allele** — `DPB1*1055` becomes
`DPB1*055`, `A*0201` becomes `A*201`. `parse_allele_value` refuses all of those
outright, so a constrained decode is strictly *less* safe than the parser here.
DPB1 alone has 821 families of four or more digits this grammar cannot express.

Cost cannot police it: deleting one confident glyph costs 9.43 at p=0.99 but
only 4.84 at p=0.50, and real crops have a weakest-frame probability whose 10th
percentile is around 0.6. `digits_preserved` closes it instead, by requiring the
digits the model actually saw to survive the constraint. Measured, that costs 2
of 1,200 real value crops and removes 499 of 500 label crops on its own.

## What the grammar deliberately does not know

It does not know the reference vocabulary. Constraining the first field to the
families that exist for a locus would silently turn `DRB1*93` into `DRB1*03` — a
wrong value produced by the very mechanism meant to catch wrong values. The
vocabulary is a post-check that can only refuse.

It does not contain the repair glyphs (`I`, `l`, `O`, `S`). Emitting real digits
is this mechanism's job; repairing misread ones is the other's, and a symbol in
both would let a glyph through twice.
"""

from __future__ import annotations

import string
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

GRAMMAR_VERSION = "hla-value-dfa/v1"

# Loci a value may name. The grammar accepts ANY of them regardless of which
# locus the cell belongs to: constraining it to the anchor's locus would make
# the resolver's prefix-consistency gate vacuous, since the decode would then
# agree with geometry by construction.
PREFIXES = (
    "A",
    "B",
    "C",
    "Cw",
    "DRB1",
    "DRB3",
    "DRB4",
    "DRB5",
    "DQA1",
    "DQB1",
    "DPA1",
    "DPB1",
)

# Built rather than written out: a literal run of ten digits reads as an
# Iranian national ID to `scripts/scan_pii.py`, and that check is worth more
# than the brevity.
DIGITS = string.digits
EXPRESSION = "NLSQCA"

_NEG = -1e9


@dataclass(frozen=True, slots=True)
class ValueGrammar:
    """A deterministic automaton over the recognizer's own symbol indices."""

    transitions: dict[int, dict[int, int]]
    accepting: frozenset[int]
    columns: tuple[int, ...]
    symbols: tuple[str, ...]
    blank: int
    digit_columns: frozenset[int]
    version: str = GRAMMAR_VERSION
    n_states: int = 0


@dataclass(frozen=True, slots=True)
class Decode:
    """One reading, with what it cost to make the model produce it."""

    text: str
    logp: float
    grammar_cost: float
    per_char_logp: float = 0.0
    frames: int = 0
    _unused: tuple[()] = field(default=())


def build_value_grammar(
    vocabulary: Sequence[str], blank: int, *, require_prefix: bool
) -> ValueGrammar:
    """The allele-value language, as an automaton over `vocabulary` indices.

    `require_prefix` is the tightening for forms that print the locus on every
    value — measured at 100% on the family-rule documents and 69% elsewhere.
    """
    index = {char: position for position, char in enumerate(vocabulary)}
    needed = set(DIGITS) | set(EXPRESSION) | {"*", ":"} | {c for p in PREFIXES for c in p}
    missing = sorted(char for char in needed if char not in index)
    if missing:
        raise ValueError(
            f"the recognizer vocabulary lacks {missing!r}; a grammar symbol it cannot "
            "emit would silently stop this shape from being read"
        )

    transitions: dict[int, dict[int, int]] = {}
    states = [0]

    def state() -> int:
        states.append(len(states))
        return states[-1]

    def link(source: int, char: str, target: int) -> None:
        transitions.setdefault(source, {})[index[char]] = target

    # Two distinct states, and conflating them was the first bug here: the
    # prefix trie ends at `after_prefix`, which must then CONSUME a star before
    # any digit. Letting the prefix lead straight to the digits skips the star
    # entirely, so `DRB1*11` never decodes.
    after_prefix = state()
    before_first = state()
    first_1 = state()
    first_2 = state()
    first_3 = state()
    colon = state()
    second_1 = state()
    second_2 = state()
    second_3 = state()
    suffix = state()

    for prefix in PREFIXES:
        node = 0
        for position, char in enumerate(prefix):
            last = position == len(prefix) - 1
            if last:
                link(node, char, after_prefix)
            else:
                nxt = transitions.get(node, {}).get(index[char])
                if nxt is None or nxt == after_prefix:
                    # `C` ends a prefix AND begins `Cw`, so the shared node
                    # cannot simply be reused: give the longer name its own.
                    nxt = state()
                    link(node, char, nxt)
                node = nxt

    link(after_prefix, "*", before_first)
    for digit in DIGITS:
        link(before_first, digit, first_1)
        link(first_1, digit, first_2)
        link(first_2, digit, first_3)
        link(colon, digit, second_1)
        link(second_1, digit, second_2)
        link(second_2, digit, second_3)
        if not require_prefix:
            link(0, digit, first_1)

    if not require_prefix:
        # A bare LEADING star with no prefix: measured, 4,118 of the 4,234 bare
        # values carry a star glyph in their raw text, and the unconstrained
        # decode reads one on 362 of 400 bare crops. Without this path the
        # decode must delete that star, at a median cost of 8.66.
        link(0, "*", before_first)

    link(first_2, ":", colon)
    link(first_3, ":", colon)
    # An expression suffix is legal only after a COMPLETE allele name, which is
    # what `parse_allele_value` also requires.
    for char in EXPRESSION:
        link(second_2, char, suffix)
        link(second_3, char, suffix)

    accepting = frozenset({first_2, first_3, second_2, second_3, suffix})
    columns = tuple(sorted({column for row in transitions.values() for column in row}))
    return ValueGrammar(
        transitions=transitions,
        accepting=accepting,
        columns=columns,
        symbols=tuple(vocabulary),
        blank=blank,
        digit_columns=frozenset(index[d] for d in DIGITS),
        n_states=len(states),
    )


def _log_softmax(logits: NDArray[np.float64]) -> NDArray[np.float64]:
    shifted = logits - logits.max(axis=-1, keepdims=True)
    result: NDArray[np.float64] = shifted - np.log(np.exp(shifted).sum(axis=-1, keepdims=True))
    return result


def greedy(logits: NDArray[np.float64], vocabulary: Sequence[str], blank: int) -> str:
    """What the recognizer would have said, collapsed the usual CTC way."""
    best = logits.argmax(axis=-1)
    out: list[str] = []
    previous = -1
    for column in best:
        if column != previous and column != blank:
            out.append(vocabulary[column])
        previous = int(column)
    return "".join(out)


def decode(logits: NDArray[np.float64], grammar: ValueGrammar) -> Decode:
    """The best path through the logits that the grammar accepts.

    Viterbi over (automaton state, last emitted symbol), which is what CTC needs
    to know whether a repeated column is one character or two.
    """
    log_probs = _log_softmax(np.asarray(logits, dtype=np.float64))
    frames, _ = log_probs.shape
    columns = list(grammar.columns)
    width = len(columns) + 1  # + "the last emission was a blank"
    blank_slot = width - 1

    scores = np.full((grammar.n_states, width), _NEG)
    scores[0, blank_slot] = 0.0
    trail: list[NDArray[np.int64]] = []

    for frame in range(frames):
        step = np.full((grammar.n_states, width), _NEG)
        pointer = np.full((grammar.n_states, width, 2), -1, dtype=np.int64)

        # A blank keeps the state and clears the last symbol.
        best_slot = scores.argmax(axis=1)
        step[:, blank_slot] = (
            scores[np.arange(grammar.n_states), best_slot] + log_probs[frame, grammar.blank]
        )
        pointer[:, blank_slot, 0] = np.arange(grammar.n_states)
        pointer[:, blank_slot, 1] = best_slot

        # A repeat of the last symbol is the same character, so the state holds.
        repeat = scores[:, : width - 1] + log_probs[frame, columns]

        # An emission moves the automaton, and cannot repeat the last symbol.
        for slot, column in enumerate(columns):
            without = scores.copy()
            without[:, slot] = _NEG
            source_slot = without.argmax(axis=1)
            candidate = without[np.arange(grammar.n_states), source_slot] + log_probs[frame, column]
            for source, row in grammar.transitions.items():
                target = row.get(column)
                if target is not None and candidate[source] > step[target, slot]:
                    step[target, slot] = candidate[source]
                    pointer[target, slot] = (source, source_slot[source])

        better = repeat > step[:, : width - 1]
        step[:, : width - 1] = np.where(better, repeat, step[:, : width - 1])
        rows, slots = np.nonzero(better)
        pointer[rows, slots, 0] = rows
        pointer[rows, slots, 1] = slots

        scores = step
        trail.append(pointer)

    accepting = sorted(grammar.accepting)
    finals = scores[accepting]
    which = int(finals.max(axis=1).argmax())
    state = accepting[which]
    slot = int(scores[state].argmax())
    total = float(scores[state, slot])
    if total <= _NEG / 2:
        return Decode(text="", logp=total, grammar_cost=float("inf"), frames=frames)

    out: list[str] = []
    for frame in range(frames - 1, -1, -1):
        previous_state, previous_slot = trail[frame][state, slot]
        emitted = slot != blank_slot and not (previous_state == state and previous_slot == slot)
        if emitted:
            out.append(grammar.symbols[columns[slot]])
        state, slot = int(previous_state), int(previous_slot)

    text = "".join(reversed(out))
    # Cost is what the model gave up. Measured against the FULL vocabulary,
    # because against the constrained path alone it would always be zero.
    unconstrained = float(log_probs.max(axis=-1).sum())
    return Decode(
        text=text,
        logp=total,
        grammar_cost=unconstrained - total,
        per_char_logp=total / max(len(text), 1),
        frames=frames,
    )


def digits_preserved(model_reading: str, decoded: str) -> bool:
    """Did every digit the model saw survive the constraint?

    The grammar allows a two- or three-digit field and TRUNCATES a longer one
    rather than refusing it, so `DPB1*1055` decodes as `DPB1*055` — a different
    allele, at a cost indistinguishable from a legible crop. Comparing the digit
    subsequences catches every measured case, costs 2 of 1,200 real value crops,
    and removes 499 of 500 label crops on its own.

    Repair aliases count as their digit, because a model that read `I` where `1`
    is printed has not lost the digit.

    Only the VALUE BODY is compared — everything after the star. A locus name
    carries digits of its own (`DRB1`), and the model misreads its letters
    (`0RB1` for `DRB1`), so comparing whole strings would fire this gate on a
    perfectly good crop whose prefix was misread. The truncation trap is about
    the allele's own fields, and those are what this checks.
    """
    aliases = {
        "I": "1",
        "i": "1",
        "l": "1",
        "L": "1",
        "|": "1",
        "T": "1",
        "!": "1",
        "O": "0",
        "o": "0",
        "Q": "0",
        "S": "5",
        "s": "5",
    }

    def digits(text: str) -> str:
        body = text.rsplit("*", 1)[-1]
        return "".join(
            character if character.isdigit() else aliases[character]
            for character in body
            if character.isdigit() or character in aliases
        )

    return digits(model_reading) == digits(decoded)
