# Current project state

**Updated:** 2026-09-05 (fourth session of the day)
**Canonical phase:** MVP-HIST
**Active task:** OCR-GEOM-001 (`docs/exec-plans/active/OCR-GEOM-001-geometry-and-drbx-row.md`); MEDIA-001/DEDUPE-001 stay READY

## Goal now
Validate what is extracted, and fix what the labels show. 220 of the pack's
1,650 cells are labelled (HA-008). Each session traces every non-correct cell
to a root cause and fixes it where the corpus bears it out (ADR 0009 §7). The
fourth found that the instrument itself was part of the problem: the page had
shown no crop for 50 of the 220 answers, and a pack rebuild used to orphan the
labels entirely.

## Locked facts
- **The archive is present**, local-only and gitignored, at
  `data/raw/ChatExport_2026-08-31`: 23,566 unique images, 90% above 900 px.
- **The source layer is parsed (HIST-001, HIST-002).** 180,441 messages and
  3,456 service events, **zero unparsed fragments**, into `source.sqlite`;
  re-import is a no-op. 23,565 of 23,566 documents are linked to the messages
  that posted them (110,050 rows, mean 4.7 each), and 18,799 have caption text
  the review pack shows.
- **Extraction (ADR 0008, 0009 §7):** `facts.sqlite` refreshed in place three
  times on 2026-09-05 (`refresh_facts.py`; snapshots beside it). It prints the
  per-locus comparison and names a stop signal, and that comparison is part of
  the procedure: it caught a prefix bug that had made the letterhead's `LAB` an
  HLA-B anchor on 9,817 documents before it shipped. The third refresh's stop
  signal was the later passes' own writes being reset, all 15 swaps DRB5
  presence reverting to the row rule — re-run the passes in the order below.
  **RESOLVED 82,480 → 110,893** across the session.
- **Page geometry (`rulings/v3+lsd+sweep`):** sweep corroborates within 2°,
  agreement calibrated on photographs (3°/0.7). 6,511 ROTATE / 14,139 STRAIGHT
  / 2,916 UNCERTAIN; 1,591 levelled (KI-024). A tilt from stored boxes is
  biased (KI-025).
- **Recognizers, against the reviewer's labels** (67 value cells,
  `ENGINE_BENCH_2026-09-05.md`): **PP-OCRv6-medium 65 exact (97%)**, the
  pipeline as it ships 57, PP-OCRv5-server 55, Qwen3-VL-4B 52, Tesseract 32,
  our own recognizer 14. No pair ever agreed on a wrong value, which is what
  licenses every two-engine gate below.
- **The decode and the confirmers.** `confirm_pass.py` has three targets
  (resolved, proposals, drbx); `promote_proposals.py` promotes the CONFIRMED
  proposals — never on a LOW page, re-judged with admissibility, withdrawn when
  an equal-or-better reader disagrees (`ENGINE_RANK`). Crops stay axis-aligned:
  the upright-crop ablation was a wash.
- **The DRB3/4/5 row prints gene names** (22,017 vs 75 bare numbers); grammar
  v2 waits on HA-011. `drbx_reread.py` re-reads a gene resting on the S-for-5
  repair and takes the digit only when it IS a digit: 1,992 rows rewritten.
- **The printed table is read as a grid (`ocr/lattice.py`).** The rulings
  place a label the recognizer could not read (**+2,272 cells**, 0 values
  swapped) and the second DRB3/4/5 slot, which ink certifies ABSENT when it is
  paper (`drbx_ink_pass.py`: **4,540 genes**). `cell_ink_pass.py` measures the
  ~24,000 empty labelled cells and **writes no fact**: `NOT_TESTED` is HA-009's
  per-laboratory verdict, so HA-012 asks the human.
- **Role resolves on 7,521 documents** (55% of those typed on 3+ loci).
- **Accuracy is still unvalidated (KI-012); this is the binding constraint.**
  The reviewer's 220-cell export scored **84 correct** as the pack showed it,
  103 against the database at the start of this session and **107 correct / 86
  correct abstentions / 14 missed / 4 partial / 9 contradicted** at its end.
  Seven of the nine contradictions are HA-014: cells marked NOT_PRINTED where
  the page evidence says otherwise, and **the page had shown no crop for 50 of
  the 220** because the pipeline had found neither label nor value there. The
  blind golden corpus waits on a person.
- **Two reading refusals now get a second opinion (`reread_refused.py`).** A
  first field that is not an allele family, and a candidate that does not parse:
  5,145 cells holding boxes nobody looked at again. Both PP-OCRv6 and
  PP-OCRv5-server must state the same value, and it must parse, be admissible
  and differ from what was refused. Single-engine yield was 97% and two-engine
  75%; the gap is the part nothing corroborated. **+2,926 cells**, resumable by
  its own table so a refresh costs no engine time.
- **A bare `A`, `B` or `C` can be a locus label** when the page's structure says
  so: the label column of a form spelling out two other loci, an allele on its
  row, and two such letters stacked. The text matcher still refuses them.
  Ablated over 4,000 documents: 106 cells gain a value, none change. Ownership
  between two aligned labels now needs a quarter-label-height margin, so the
  tilt of a photograph cannot decide which gene owns a value (17 more cells).
- **A pack rebuild pins the labelled documents (`--keep-labelled`).** The
  sample is stratified by fact status, so a refresh reshuffles it: 11 of 220
  labels survived the first rebuild, 220 with the flag, and 189 now show a
  crop rather than 170.
- **Two form facts constrain the product:** DPA1/DPB1 printed, never filled
  (HA-009); the letterhead disclaims its blood-group field (KI-014). The
  zero-fact documents are mostly not reports (KI-018): ~170 of 4,944
  recoverable. Geometry determines locus, not text.

## Decided (operator delegated)
HA-003 resolution bands (MID provisional) · HA-005 names as a salted hash ·
HA-006 IMGT 3.62 · HA-009 untested-locus policy (`HUMAN_ACTIONS.md`, Closed).

## Human actions open
**HA-014** re-answer the seven NOT_PRINTED cells (they carry crops now).
**HA-013** Google Vision: no such key is in `.env`, and
`CV_RESEARCH_2026-09-05.md` s6 still forbids sending an image off the machine.
**HA-008 label the pack** — 220/1,650 done. **HA-007** the blind golden corpus.
**HA-011** the DRB3/4/5 grammar. Then HA-004 (blocks V1-MATCH), HA-001/2/10.

## Completed foundation
- P0 harness repair, P1 autonomy, P2 test depth (12-step gate, invariant
  traceability, coverage 65% / medical modules 100%, PII scanner, bandit,
  gitleaks, osv-scanner, mutmut).
- Derived local stores, all gitignored: `ocr_pass`, `facts`, `source`,
  `geometry` (sqlite), `data/review/hla_pack/`, `data/review/queue.json`.
  Committed measurements the thresholds rest on live in `config/`.

## Next actions
1. **Human: HA-014** (re-answer the seven), **HA-013** (the Vision key and the
   policy), then keep labelling (HA-008). Score with `scripts/pack_score.py`
   for the pack's view and against `facts.sqlite` for the current one.
2. **Pass order after any refresh:** `decode_pass`, the three `confirm_pass`
   targets on tesseract5/ppocrv5/ppocrv6, `promote_proposals`, `drbx_ink_pass`,
   `cell_ink_pass`, `drbx_reread`, `reread_refused`. Rebuild the pack with
   `--keep-labelled <export>` or the labels are orphaned.
3. Agent: the 14 remaining misses are 6 with no anchor (the label is unreadable
   and no rule reaches it), 6 found-and-refused (ownership by reading-axis
   distance, `max_values`, two anchors on one row, a star-less value), 1 empty
   row and 1 unparsable. Then M6 after HA-011, KI-023, KI-027, MEDIA-001,
   DEDUPE-001, ENTITY-001. Human: HA-004 before matching beyond the ABO gate.

## Last verified baseline
`python scripts/verify_repo.py` PASS, 12 steps, 2026-09-05 (fourth session).
Re-run it yourself; this records a past result, not the current environment.
