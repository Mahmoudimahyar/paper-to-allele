# What the labels measure, and where they live

**Measured:** 2026-09-09. **Annotator:** one, unadjudicated.
**Instrument:** `scripts/review_pack.py` review packs, scored by
`scripts/label_score.py` against the live fact store.

This records the first measurement of the pipeline that covers the two fields
the matcher gates on, and it changes what the project believes its problem is.

---

## 1. The headline

The extraction is **accurate and incomplete**, and it is incomplete in the one
place that decides whether a pair can be ranked at all.

| Field | A person read it on | Pipeline agreed | Pipeline had nothing | Pipeline contradicted |
|---|---|---|---|---|
| HLA cells | 861 | 717 (83.3%) | 120 | 3 (0.3%) |
| Blood group | 102 | 51 (50%) | 51 | **0** |
| Role | 117 | 98 (84%) | 17 | 2 |

Blood group is never read wrongly and is missed half the time. That asymmetry is
the whole finding. Precision is not the problem anywhere in this table; recall
is, and the blood group is the worst of the three.

**Why it matters more than the HLA numbers.** The ABO gate runs before the HLA
heuristic. A pair whose group is unknown on either side lands in
`INSUFFICIENT_ABO` and is never ranked, whatever its typing. On the 2026-09-08
Gold build, 72.6% of evaluated pairs land there. That figure was previously
read as a fact about the archive. It is not. It is a fact about what the
extractor managed to read, and this measurement says the extractor finds about
half of what is on the page.

---

## 2. Where the labels are, and the risk to them

**They live in the browser until they are exported.** The review page keeps
answers in `localStorage`, keyed by pack id and annotator. Clearing site data,
a private window, or a different browser loses them with no warning and no
recovery. There is no server. Export early and often; the page's export button
writes a `golden-labels/v1` file.

**The archive** is `data/review/labels/`, gitignored, with a `MANIFEST.json`
recording pack, annotator, export time, counts and a SHA-256 per file. Copies
are verbatim; nothing is rewritten on the way in. Re-running the copy is safe
and reports `already stored` for anything unchanged.

Files are named `<pack id>__<annotator>__<export timestamp>.json`, so two
exports of the same pack cannot overwrite each other. That matters: a later
export of a pack is a superset, not a replacement, and keeping both lets a
mistake be traced rather than guessed at.

**This is patient data.** Every label is an HLA typing, a blood group or a role
belonging to a real person. It may not be committed, pasted into a report, or
sent anywhere the archive itself would not go. `scripts/scan_pii.py` will not
catch it: that scanner looks for national identifiers and mobile numbers, not
for clinical values.

**What is stored today:** 8 exports, 128 distinct documents, 1,408 distinct
cells, 23 notes. Cells are deduplicated across rounds by cell id, so the raw
export total of 2,420 collapses to 1,408 once a pack labelled twice is counted
once.

---

## 3. Why the blood group is missed

Every miss carries the pipeline's own stated reason, and they fall into two
groups of very different character.

| Reason | Share of the 51 misses | Corpus-wide population |
|---|---|---|
| no blood-group field label on this document | 30 | 8,914 |
| the field is printed but its cell could not be read | 18 | 2,971 |
| an Rh sign with no group letter in its cell | 2 | 139 |
| more than one blood-group value in a single cell | 1 | 85 |

The first line is the serious one. The pipeline is not saying "I read the cell
and it was empty". It is saying **it never found a blood-group label on the
page**, and a person then read a group off that same page. On the sample, that
is a label detector missing labels rather than pages lacking them, and it
governs 8,914 documents.

The second line is a different failure with the same symptom: the label was
found and the value beside it was not read. A reviewer note from
2026-09-09 points at a plausible shared cause — that on at least one document
the HLA-A crop was the right length while every other locus was cropped too
short to hold both alleles. A cell window that is too small would produce both
the unread blood-group cells and the missed second alleles counted in section 4.

**The chat is not the answer here.** Reading it exactly as the pipeline does,
its own message plus every sibling in its bundle, across all 12,468 documents
with no resolved group, the caption reader finds a group in 12. The chat is
already the largest single source of blood groups in Gold (5,498 of 8,792) and
it is exhausted. The remaining headroom is on the page.

**Where a caption still earns its place:** on 24 documents the reviewer marked
the group as not printed on the page, and the pipeline held one anyway on 13 of
them, read from the chat. Those are not disagreements. They are the caption path
doing the job the page could not.

---

## 4. The HLA cells

| Locus | Correct | Abstained | Missed | Partial | Contradicted |
|---|---|---|---|---|---|
| A | 103 | 5 | 15 | 4 | 1 |
| B | 100 | 6 | 19 | 2 | 1 |
| C | 46 | 72 | 9 | 1 | 0 |
| DRB1 | 101 | 6 | 14 | 7 | 0 |
| DQB1 | 95 | 8 | 17 | 7 | 1 |
| DQA1 | 2 | 125 | 1 | 0 | 0 |
| DRB3 | 93 | 23 | 12 | 0 | 0 |
| DRB4 | 88 | 23 | 17 | 0 | 0 |
| DRB5 | 89 | 23 | 16 | 0 | 0 |
| DPA1 / DPB1 | 0 | 256 | 0 | 0 | 0 |

`Partial` is the second allele: the pipeline held one value where the person
read two. 21 of those, concentrated at DRB1 and DQB1, which is consistent with
the crop-length note above and with KI-015.

DPA1 and DPB1 are printed on the form and never filled in, which HA-009 already
records. Their perfect abstention is the correct behaviour, not a result.

---

## 5. What this is not

**It is not a corpus-wide accuracy, and must not be quoted as one.** Review
packs are stratified to over-represent failure: documents are drawn from the
signals the pipeline itself emits when something looks wrong, with quotas that
deliberately inflate the rare and difficult strata, plus one clean-control
stratum. A number from this sample is a diagnostic of where the pipeline fails,
not an estimate of how often it fails across 23,566 documents. The corpus-wide
figure will be better than 83.3%, and nobody yet knows by how much.

**It is one annotator, unadjudicated.** The golden protocol (ADR 0009) needs two
blind labellers and a third to adjudicate; this is neither blind nor doubled,
and the reviewer sees the pipeline's proposal beside the crop, which anchors
them. KI-012 and HA-007 both stand. Treat every number here as the fastest
honest signal available, not as a published result.

**The three contradicted HLA cells and the two reversed roles are the
exceptions that matter most.** A reversed role puts a pair in the wrong
direction of the ranking, where the mismatch count is not symmetric and the
answer is therefore wrong rather than merely unlucky. Two in 117 is small and it
is not zero.

---

## 6. Reproducing this

```
.venv/Scripts/python.exe scripts/label_score.py data/review/labels/2026*.json
```

The glob deliberately excludes `MANIFEST.json`, which is not an export. Add
`--why` for one line per cell that is neither correct nor a correct abstention.

`label_score.py` scores the LIVE fact store, so these numbers move as the
pipeline moves; they are not frozen against the pack that was labelled. That is
the point of it. `pack_score.py` is the other instrument and answers the other
question: how one round looked at the moment it was cut.

---

## 7. What follows

1. **The label detector, not the recognizer.** 8,914 documents where no
   blood-group label was found is the largest single lever on the matcher that
   this project has measured. It is worth a targeted pack before it is worth any
   code.
2. **The cell window.** One reviewer note and 21 partial cells point the same
   way. Measure the crop against the printed cell before changing it.
3. **More labels on the missing-group population specifically.** 102 documents
   carrying a blood group is enough to see a 50% miss and not enough to
   apportion it between the two causes with any confidence.
