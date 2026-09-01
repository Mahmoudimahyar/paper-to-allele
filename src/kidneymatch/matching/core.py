"""Matching core placeholder.

V1 implementation must remain deterministic and may not import compensation.
The active MVP-HIST phase intentionally does not implement clinical ranking yet.
"""
from __future__ import annotations


class MatchingNotImplemented(RuntimeError):
    pass


def rank_candidates(*_: object, **__: object) -> None:
    raise MatchingNotImplemented("MATCH-001 is not active in MVP-HIST")
