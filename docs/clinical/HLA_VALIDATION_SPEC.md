# HLA Validation and Nomenclature Specification

## 1. Reference authority
Pin **IPD-IMGT/HLA release 3.62 (`imgt_version="3620"`)** for the initial
implementation. Store the release number with every normalization/extraction run.

**Amended 2026-09-03 (HA-006, decided by the human operator).** The original pin
was 3.65 (2026-07). The locked `py-ard` is 1.5.5, and
`init(imgt_version="3650")` raises `IndexError` on it; 3640 fails the same way
and 3620 loads (verified on this machine, KI-011). A spec pinning a release the
build cannot load is not a pin, so the spec follows the lockfile rather than the
other way round.

This is safe for what the pin is *for*. The gate it feeds is first-field
admissibility — whether `DRB1*93` is a family that exists — and no first field
of any locus these laboratories print was added or withdrawn between 3.62 and
3.65. Raising `py-ard` to a 2.x release and re-testing 3650 is its own task,
with the OSS register and the lockfile, and it must not be done silently as a
side effect of an extraction change.

Use `py-ard` to validate/normalize historical HLA nomenclature against the pinned database. The application MUST NOT maintain a handwritten static list of all possible alleles.

## 2. Supported loci
Core:
- HLA-A
- HLA-B
- HLA-C
- HLA-DRB1
- HLA-DRB3
- HLA-DRB4
- HLA-DRB5
- HLA-DQA1
- HLA-DQB1
- HLA-DPA1
- HLA-DPB1

A raw invalid label such as `DQR1` is preserved as a source claim but not accepted as a canonical locus.

## 3. Dynamic valid vocabulary
At build/reference-import time generate:
- exact valid allele set per locus;
- valid first-field groups per locus;
- valid two-field alleles per locus;
- serology mappings when required;
- historical nomenclature mappings supported by py-ard.

For a low-resolution printed result `A*02`, accept it as low-resolution if `A*02` is a valid first-field family; do not infer a second field.

## 4. Normalization rules
Preserve three values:
- `raw_value`
- `normalized_notation`
- `resolution`

Examples:
- `A 02` → normalized `A*02`, resolution `FIRST_FIELD` when locus geometry confirms A.
- `A*02:01` remains two-field.
- `B35` may map to a serology/legacy claim only when the source type indicates antigen/serology; do not assume allele notation.

## 5. Ambiguity
If multiple valid HLA strings fit the OCR crop, status is `AMBIGUOUS_REVIEW_REQUIRED`.

Do not resolve ambiguity by:
- most common allele;
- closest donor match;
- what improves recipient ranking;
- LLM preference.

## 6. DQ representation
When only DQB1 is available, store DQB1 only. Do not claim complete HLA-DQ heterodimer typing.

When high-resolution DQA1 + DQB1 are available, construct DQ alpha/beta heterodimer candidates according to validated phasing rules. If phase is unknown, preserve ambiguity and do not pretend a single heterodimer configuration is known.

## 7. DRB3/4/5
Store DRB3, DRB4, DRB5 as separate loci/features. A form row labeled `DRB3/4/5` is a presentation grouping, not a single gene.

## 8. Reference versioning
Every MatchRun stores:
- HLA reference database version;
- matching policy version;
- normalization library version;
- input typing resolution.

Re-running with a future IPD release creates a new MatchRun; historical output remains reproducible.
