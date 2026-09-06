#!/usr/bin/env python3
"""Read whole pages with Google Cloud Vision, to measure our own detector.

**This pass sends a real report page off the machine.** It exists because
`CV_RESEARCH_2026-09-05.md` s7 records the project owner's decision to allow
exactly that, after being offered the narrower option of value crops and
choosing whole pages. The reason is in that note: the largest refusal bucket in
the pipeline is 23,719 cells whose locus label was found and whose value box
was never detected, and a crop of a box we never drew cannot tell us whether a
better detector would have drawn it.

What this pass is for, and what it is not:

* it measures a SECOND DETECTOR. Its output is stored in its own database and
  is evidence about `ocr_pass.sqlite`, never a laboratory value. Nothing here
  writes a fact, and the rule that OCR produces proposals rather than
  verification is untouched;
* it refuses to walk the corpus. Every run takes an explicit list — the
  documents behind a label export, or the documents of the review pack — so
  nothing is sent that a person did not put in the sample. An export it cannot
  read is an error, never a silently smaller sample;
* it writes only under `data/derived/`, which is the ignored tree. The stop
  hook commits with `git add -A`, so a store written anywhere else would be one
  careless flag away from committing report text;
* the key travels in the `X-Goog-Api-Key` header, never in the URL. A secret in
  a query string ends up in `Request.full_url` and in `HTTPError.url`, and — if
  the value is malformed — is printed verbatim by an `http.client.InvalidURL`
  traceback that no handler here would catch. The header has none of those
  paths, and `read_key` refuses a value that could produce them anyway.

Output goes to `data/derived/vision_pass.sqlite`, whose shape deliberately
matches `ocr_result` (normalised `[x0, y0, x1, y1]` boxes and their texts) so
that `ocr/anchors.py` can be pointed at either store and asked the same
question. It is PHI, gitignored like every other derived store, and the console
prints counts only.

Usage:
    uv run --frozen --extra hist python scripts/vision_pass.py \\
        --from-export <labels.json>          # the documents someone labelled
    uv run --frozen --extra hist python scripts/vision_pass.py --pack  # all 150
"""

from __future__ import annotations

import argparse
import base64
import http.client
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
KEY_VARIABLE = "GOOGLE_VISION_API"
ENGINE_VERSION = "google-vision/v1+DOCUMENT_TEXT_DETECTION"
# Vision's own words, not our detector's: this pass must not inherit any of our
# preprocessing, or it measures our pipeline again rather than a second opinion.
PREPROC_VERSION = "v1-none"
TIMEOUT_S = 60
RETRY_WAITS = (2, 8, 30)
# Consecutive unreachable pages before the run gives up. Without it a network
# outage spends 40s of sleeps per document over the whole sample, and the rows
# already committed mean the next run resumes where this one stopped.
MAX_CONSECUTIVE_UNREACHABLE = 3
# The only tree this pass may write to: the ignored one.
ALLOWED_OUTPUT_ROOT = ROOT / "data" / "derived"
# A key that cannot go safely into a header. Anything in this class would also
# have corrupted a query string, so it is refused rather than sent mangled.
UNSAFE_IN_KEY = re.compile(r"[\x00-\x20\x7f]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS vision_result (
    sha256          TEXT NOT NULL,
    engine_version  TEXT NOT NULL,
    rel_path        TEXT NOT NULL,
    width           INTEGER,
    height          INTEGER,
    n_boxes         INTEGER,
    boxes_json      TEXT,
    texts_json      TEXT,
    token_boxes_json TEXT,
    tokens_json     TEXT,
    confs_json      TEXT,
    full_text       TEXT,
    elapsed_ms      INTEGER,
    error           TEXT,
    created_utc     TEXT NOT NULL,
    PRIMARY KEY (sha256, engine_version)
);
"""


class MissingKey(RuntimeError):
    """The operator's key is absent, or is not a value that can be sent."""


class Rejected(RuntimeError):
    """Google refused the request itself: the key, the project or the quota.

    Distinct from an unreachable network because the answer will be the same
    for every other document. Continuing would upload the whole sample and have
    each page refused in turn.
    """


class Unreachable(RuntimeError):
    """The request never got an answer, after the retries."""


def _unquote(value: str) -> str:
    """A `.env` right-hand side: quoted whole, or up to an unquoted comment."""
    value = value.strip()
    for quote in ("'", '"'):
        if value.startswith(quote):
            closing = value.find(quote, 1)
            return value[1:closing] if closing > 0 else value[1:]
    return value.split(" #", 1)[0].strip()


def read_key(env_file: Path) -> str:
    """The API key, from the environment or the ignored `.env`.

    Parses the line the way a shell would rather than trusting `strip()`: an
    `export` prefix, a quoted value and an unquoted trailing `# comment` are all
    things a person writes in a `.env`, and each one silently corrupts a naive
    read. A value that still holds whitespace or a control character is refused
    outright, because sending a mangled secret produces a baffling 403 and
    putting one in a URL used to print it in a traceback.

    The key is never written anywhere and never appears in an error: the
    exception says only that it is absent or unusable.
    """
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key and env_file.exists():
        # utf-8-sig: a BOM on the first line otherwise hides a key that is there.
        for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            line = line[len("export ") :].lstrip() if line.startswith("export ") else line
            name, separator, value = line.partition("=")
            if not separator or name.strip() != KEY_VARIABLE:
                continue
            key = _unquote(value)
            break
    if not key:
        raise MissingKey(
            f"{KEY_VARIABLE} is not set in the environment or in {env_file.name}; "
            "see HA-013. Nothing was sent."
        )
    if UNSAFE_IN_KEY.search(key):
        raise MissingKey(
            f"{KEY_VARIABLE} holds whitespace or a control character, so it is not the key "
            "as issued. Look for a trailing comment or a line break on that line. Nothing "
            "was sent, and the value is not printed."
        )
    return key


def _quad(vertices: list[dict[str, int]], width: int, height: int) -> list[float] | None:
    """A Vision bounding polygon as a normalised axis-aligned box.

    Vision returns four vertices, and on a rotated page they are a genuine
    quadrilateral. The rest of the pipeline speaks axis-aligned boxes, so this
    takes the enclosing rectangle and records nothing it cannot support. A
    vertex omits a coordinate that is zero, so a missing key means 0.
    """
    xs = [v.get("x", 0) for v in vertices]
    ys = [v.get("y", 0) for v in vertices]
    if not xs or not ys or width <= 0 or height <= 0:
        return None
    x0, x1 = min(xs) / width, max(xs) / width
    y0, y1 = min(ys) / height, max(ys) / height
    if x1 <= x0 or y1 <= y0:
        return None
    return [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)]


# Break types Vision reports BETWEEN two of its words. Anything in this set
# separates printed tokens; anything else (including no break at all) does not.
SEPARATING_BREAKS = frozenset({"SPACE", "SURE_SPACE", "EOL_SURE_SPACE", "LINE_BREAK"})


def _word_text(word: dict) -> str:
    return "".join(symbol.get("text", "") for symbol in word.get("symbols") or [])


def _word_break(word: dict) -> str:
    """The break Vision reports after this word, from the word or its last symbol."""
    at_word = ((word.get("property") or {}).get("detectedBreak") or {}).get("type", "")
    if at_word:
        return str(at_word)
    symbols = word.get("symbols") or []
    if not symbols:
        return ""
    last = (symbols[-1].get("property") or {}).get("detectedBreak") or {}
    return str(last.get("type", ""))


def printed_tokens(payload: dict, width: int, height: int) -> tuple[list[list[float]], list[str]]:
    """Vision's words rejoined into the tokens the page actually prints.

    This matters more than it sounds. Vision returns `A*24` as three words —
    `A`, `*`, `24` — because it puts a word boundary at the punctuation, and
    `ocr/anchors.py` requires the whole token: `canonical_locus_label` refuses
    a bare `A` on purpose, and `parse_allele_value` cannot read a bare `24` as
    an allele of anything. Measured on the reviewer's 20 pages, feeding the raw
    words to the binding rule scored 1 correct cell out of 160 against our own
    detector's 62, which measures Vision's tokenisation and not its reading.

    Rejoining by geometry was tried first and is a guess: a threshold tight
    enough to leave two columns apart leaves `A` and `24` apart too. Vision
    already knows the answer and reports it — `detectedBreak` says whether a
    space follows each word — so this uses that instead of measuring gaps.
    """
    boxes: list[list[float]] = []
    texts: list[str] = []
    annotation = payload.get("fullTextAnnotation") or {}
    for page in annotation.get("pages") or []:
        for block in page.get("blocks") or []:
            for paragraph in block.get("paragraphs") or []:
                run_boxes: list[list[float]] = []
                run_text: list[str] = []
                for word in paragraph.get("words") or []:
                    box = _quad(
                        (word.get("boundingBox") or {}).get("vertices") or [], width, height
                    )
                    if box is not None:
                        run_boxes.append(box)
                        run_text.append(_word_text(word))
                    if _word_break(word) in SEPARATING_BREAKS and run_boxes:
                        boxes.append(_enclosing(run_boxes))
                        texts.append("".join(run_text))
                        run_boxes, run_text = [], []
                if run_boxes:
                    boxes.append(_enclosing(run_boxes))
                    texts.append("".join(run_text))
    return boxes, texts


def _enclosing(boxes: list[list[float]]) -> list[float]:
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def parse_response(payload: dict, width: int, height: int) -> dict[str, object]:
    """Word boxes, the printed tokens they make, and the page's full text.

    `textAnnotations[0]` is the whole page in one entry; the words follow. Both
    the words and the rejoined tokens are kept: the words are what Vision
    actually returned, and the tokens are what our rules can read.
    """
    annotations = payload.get("textAnnotations") or []
    boxes: list[list[float]] = []
    texts: list[str] = []
    for entry in annotations[1:]:
        box = _quad((entry.get("boundingPoly") or {}).get("vertices") or [], width, height)
        if box is None:
            continue
        boxes.append(box)
        texts.append(entry.get("description") or "")
    token_boxes, tokens = printed_tokens(payload, width, height)
    full = (payload.get("fullTextAnnotation") or {}).get("text") or (
        annotations[0].get("description") if annotations else ""
    )
    return {
        "boxes": boxes,
        "texts": texts,
        "token_boxes": token_boxes,
        "tokens": tokens,
        "full_text": full,
    }


def google_said(problem: urllib.error.HTTPError) -> str:
    """Google's own explanation of a refusal, with its reason code.

    Worth the few lines: the first refusal this pass met was
    `API_KEY_SERVICE_BLOCKED`, which is a restriction on the key rather than
    anything about the request, and a bare `HTTP 403` sends the reader looking
    in the wrong place. Nothing secret can arrive here — the key is a header on
    the way out and appears in no response.
    """
    try:
        body = json.loads(problem.read().decode("utf-8") or "{}")
    except (ValueError, OSError):
        return ""
    detail = body.get("error", {}) if isinstance(body, dict) else {}
    if not isinstance(detail, dict):
        return ""
    details = detail.get("details", [])
    reason = next(
        (
            entry.get("reason", "")
            for entry in (details if isinstance(details, list) else [])
            if isinstance(entry, dict) and str(entry.get("@type", "")).endswith("ErrorInfo")
        ),
        "",
    )
    message = str(detail.get("message", ""))[:200]
    return f"{reason}: {message}" if reason else message


def annotate(image_bytes: bytes, key: str) -> dict:
    """One page to Vision.

    Raises `Rejected` when Google refuses the request itself, because that
    answer will be identical for every other page and the caller must stop
    rather than upload the rest. Raises `Unreachable` when the retries are
    exhausted without an answer.
    """
    body = json.dumps(
        {
            "requests": [
                {
                    "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                    "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                }
            ]
        }
    ).encode("utf-8")
    last = ""
    for wait in (*RETRY_WAITS, None):
        request = urllib.request.Request(  # noqa: S310  (https, fixed endpoint)
            ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json", "X-Goog-Api-Key": key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            responses = payload.get("responses") or [{}]
            first = responses[0]
            if "error" in first:
                raise Rejected(f"vision: {first['error'].get('message', 'unknown')}")
            return first
        except urllib.error.HTTPError as problem:  # pragma: no cover - network
            last = f"HTTP {problem.code} {google_said(problem)}".strip()
            if problem.code in (400, 401, 403, 429):
                raise Rejected(f"vision refused the request: {last}") from None
        except (
            urllib.error.URLError,
            OSError,
            http.client.HTTPException,
            json.JSONDecodeError,
        ) as problem:
            # `urlopen` lets `HTTPException` through from `getresponse()`, and
            # `TimeoutError` is an `OSError`. A narrower tuple missed both, so
            # an ordinary transient fault escaped the retry loop entirely.
            last = problem.__class__.__name__
        if wait is None:
            break
        time.sleep(wait)
    raise Unreachable(f"no answer after {len(RETRY_WAITS) + 1} attempts: {last}")


def documents_from_export(
    exports: list[Path], facts: Path
) -> tuple[list[tuple[str, str]], list[Path]]:
    """(sha256, rel_path) per document behind a label export, and what failed.

    An export that cannot be read comes back as a failure rather than being
    skipped: silently shrinking the sample would look like a completed run over
    fewer pages, which is the very kind of quiet difference this pass exists to
    detect in the pipeline.
    """
    prefixes: set[str] = set()
    failed: list[Path] = []
    for source in exports:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failed.append(source)
            continue
        if not isinstance(payload, dict):
            failed.append(source)
            continue
        for key in ("cells", "labels"):
            entries = payload.get(key) or {}
            for cell_id in entries if isinstance(entries, dict) else []:
                head = str(cell_id).rsplit(":", 1)[0]
                if len(head) == 16:
                    prefixes.add(head)
    return _resolve(prefixes, facts), failed


def documents_from_pack(pack: Path, facts: Path) -> tuple[list[tuple[str, str]], list[Path]]:
    """Every document of a review pack, or the pack path if it cannot be read."""
    try:
        payload = json.loads(pack.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], [pack]
    documents = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(documents, list):
        return [], [pack]
    prefixes = {
        str(entry.get("sha256", ""))[:16]
        for entry in documents
        if isinstance(entry, dict) and len(str(entry.get("sha256", ""))) >= 16
    }
    return _resolve(prefixes, facts), []


def _resolve(prefixes: set[str], facts: Path) -> list[tuple[str, str]]:
    if not prefixes:
        return []
    con = sqlite3.connect(f"file:{facts.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT DISTINCT sha256, rel_path FROM document WHERE extraction_version='facts/v1'"
    ).fetchall()
    con.close()
    return sorted((sha, rel) for sha, rel in rows if sha[:16] in prefixes)


def _record(
    con: sqlite3.Connection,
    row: tuple[str, str, int, int],
    started: float,
    now: str,
    *,
    parsed: dict[str, object] | None = None,
    problem: str | None = None,
) -> int:
    """One row, whether the page was read or refused. Returns the box count."""
    sha, rel, width, height = row
    boxes = parsed["boxes"] if parsed else []
    con.execute(
        "INSERT OR REPLACE INTO vision_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            sha,
            ENGINE_VERSION,
            rel,
            width,
            height,
            len(boxes),  # type: ignore[arg-type]
            json.dumps(boxes) if parsed else None,
            json.dumps(parsed["texts"]) if parsed else None,
            json.dumps(parsed["token_boxes"]) if parsed else None,
            json.dumps(parsed["tokens"]) if parsed else None,
            None,
            parsed["full_text"] if parsed else None,
            int((time.monotonic() - started) * 1000),
            problem,
            now,
        ),
    )
    con.commit()
    return len(boxes)  # type: ignore[arg-type]


def run(
    documents: list[tuple[str, str]],
    export_dir: Path,
    out: Path,
    key: str,
    *,
    limit: int | None = None,
) -> Counter[str]:
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

    con = sqlite3.connect(out)
    con.executescript(SCHEMA)
    done = {
        row[0]
        for row in con.execute(
            "SELECT sha256 FROM vision_result WHERE engine_version=? AND error IS NULL",
            (ENGINE_VERSION,),
        )
    }
    unread = [(sha, rel) for sha, rel in documents if sha not in done]
    # `is not None`, not truthiness: `--limit 0` asked for nothing and used to
    # send the entire sample.
    work = unread if limit is None else (unread[:limit] if limit > 0 else [])
    tally: Counter[str] = Counter()
    tally["already read on an earlier run"] = len(documents) - len(unread)
    tally["held back by --limit"] = len(unread) - len(work)
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    silent_in_a_row = 0
    for index, (sha, rel) in enumerate(work, 1):
        path = export_dir / rel
        try:
            raw = path.read_bytes()
            with Image.open(path) as image:
                width, height = image.size
        except (OSError, UnidentifiedImageError):
            tally["image unreadable"] += 1
            continue
        started = time.monotonic()
        try:
            payload = annotate(raw, key)
        except (Rejected, Unreachable) as problem:
            _record(con, (sha, rel, width, height), started, now, problem=str(problem))
            fatal = isinstance(problem, Rejected)
            tally[f"{'refused' if fatal else 'no answer'}: {problem}"[:66]] += 1
            if fatal:
                print(f"  stopping: {problem}", flush=True)
                break
            silent_in_a_row += 1
            if silent_in_a_row >= MAX_CONSECUTIVE_UNREACHABLE:
                print(
                    f"  stopping: {silent_in_a_row} pages in a row got no answer; the next "
                    "run resumes from here",
                    flush=True,
                )
                break
            continue
        silent_in_a_row = 0
        parsed = parse_response(payload, width, height)
        tally["word boxes"] += _record(con, (sha, rel, width, height), started, now, parsed=parsed)
        tally["pages read"] += 1
        if index % 10 == 0 or index == len(work):
            print(f"  {index}/{len(work)} pages", flush=True)
    con.close()
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", type=Path, default=ROOT / "data/derived/facts.sqlite")
    parser.add_argument("--export", type=Path, default=ROOT / "data/raw/ChatExport_2026-08-31")
    parser.add_argument("--out", type=Path, default=ALLOWED_OUTPUT_ROOT / "vision_pass.sqlite")
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--pack-json", type=Path, default=ROOT / "data/review/hla_pack/pack.json")
    parser.add_argument(
        "--from-export",
        type=Path,
        nargs="*",
        default=None,
        help="golden-labels exports; their documents are the sample",
    )
    parser.add_argument("--pack", action="store_true", help="every document of the review pack")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="print what a blocked key means and how to unblock it, then run",
    )
    args = parser.parse_args()

    if not args.out.resolve().is_relative_to(ALLOWED_OUTPUT_ROOT.resolve()):
        print(
            f"--out must be under {ALLOWED_OUTPUT_ROOT.relative_to(ROOT).as_posix()}/, the "
            "ignored tree. This store holds the text of real report pages, and the stop hook "
            "commits with `git add -A`. Nothing was sent."
        )
        return 2

    documents: list[tuple[str, str]] = []
    failed: list[Path] = []
    if args.from_export:
        found, bad = documents_from_export(list(args.from_export), args.facts)
        documents += found
        failed += bad
    if args.pack:
        found, bad = documents_from_pack(args.pack_json, args.facts)
        documents += found
        failed += bad
    if failed:
        print("could not read, and the sample would have been silently smaller:")
        for path in failed:
            print(f"  {path}")
        return 2
    documents = sorted(set(documents))
    if not documents:
        print(
            "no documents named. This pass never walks the corpus: pass "
            "--from-export <labels.json> or --pack (CV_RESEARCH s7)."
        )
        return 2
    try:
        key = read_key(args.env)
    except MissingKey as problem:
        print(problem)
        return 2
    if args.explain:
        print(
            "A run that reports API_KEY_SERVICE_BLOCKED has a valid key whose API\n"
            "restriction list does not include the Cloud Vision API. In the Google\n"
            "Cloud console: APIs & Services > Credentials > the key > API\n"
            "restrictions > add Cloud Vision API, and check the API is enabled\n"
            "under Enabled APIs & services. A refused page has still been sent in\n"
            "the request body before the key is checked, which is why the run\n"
            "stops at the first refusal instead of offering up the rest."
        )
    print(f"sending {len(documents)} whole pages to Google Cloud Vision (HA-013, CV_RESEARCH s7)")
    tally = run(documents, args.export, args.out, key, limit=args.limit)
    for name, count in sorted(tally.items()):
        if count:
            print(f"  {name:<58}{count:>8,}")
    print(f"stored in {args.out.name}; it is PHI and gitignored, and writes no fact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
