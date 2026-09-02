# Open-Source Dependency Policy and Initial Register

## Policy
Reuse mature open-source software for generic infrastructure. Write custom code only for domain-specific behavior or where a dependency fails quality/security/license review.

Every dependency requires:
- exact purpose;
- license;
- pinned version/lock hash;
- maintenance/security review;
- data/network access review;
- replacement plan.

## Initial decisions
| Area | Library/tool | Decision |
|---|---|---|
| Web | Django 5.2 LTS | ADOPT |
| DB | PostgreSQL 18 | ADOPT |
| Dynamic HTML | HTMX | ADOPT |
| Styling | Bootstrap RTL | ADOPT |
| Small JS | Alpine.js | NARROW USE |
| Telegram HTML parse | lxml / BeautifulSoup | ADOPT |
| Batch ETL | Polars + Parquet | ADOPT after dependency install/spike |
| Images | Pillow + OpenCV | ADOPT |
| Primary Persian OCR | PaddleOCR PP-OCRv5 Arabic recognizer | **BENCHMARKED 2026-09-01 — 6,045 ms/img, 6x slower than RapidOCR; needs `enable_mkldnn=False` to run at all on Zen 5. Best HLA recall (61.8%) but too slow for the iterate loop.** |
| Second OCR | Tesseract 5 (`fas`, `eng`) | **BENCHMARKED — 283 ms/img, the ONLY engine that reads Persian (34.5%). Contributes 0 extra HLA values. Adopt for Persian METADATA, not for HLA cells.** |
| VLM fallback | PaddleOCR-VL | ADOPT after resource/accuracy benchmark |
| OCR alternative | Surya | BENCHMARK, not mandatory |
| Latin/HLA OCR | RapidOCR (PP-OCR ONNX) | **BENCHMARKED — 984 ms/img, 47.7% HLA recall, no PaddlePaddle dependency. Fastest usable Latin path; recommended default.** |
| HLA nomenclature | py-ard | ADOPT with pinned IPD release and license review |
| Fuzzy text | RapidFuzz | ADOPT |
| Perceptual hashing | imagehash or `perception` | SPIKE then pin one |
| Testing | pytest, Hypothesis, pytest-bdd | ADOPT |
| Test order independence | pytest-randomly | ADOPT — pinned 3.16 |
| Coverage | pytest-cov + coverage | ADOPT — repo ratchet 65%, medical modules 100% |
| Mutation testing | mutmut 3.7 | ADOPT — scoped to hla/matching/ocr/media. LINUX ONLY (os.fork) |
| Python SAST | bandit[toml] 1.9 | ADOPT — pre-commit + verify gate |
| Secret scanning | gitleaks 8.30 | ADOPT — staged in pre-commit, full history in CI |
| Dependency CVEs | osv-scanner | ADOPT — reads uv.lock directly, no export step |
| PII detection | `scripts/scan_pii.py` (stdlib) | CUSTOM — Iranian national-ID mod-11 checksum + mobile |
| Browser E2E | Playwright | ADOPT V3+ |
| HTTP schema tests | Schemathesis | ADOPT when API exists |
| TLS | Caddy | ADOPT |
| Backups | restic | ADOPT |

## Explicitly not used in early versions
- React/Vue SPA framework
- Kubernetes
- microservices
- Kafka
- Elasticsearch
- Redis/Celery unless PostgreSQL-backed jobs fail durability needs
- general LLM as matching authority
- cloud OCR as default


## Security tooling decisions (2026-09-01)

- **bandit AND semgrep are not substitutes.** bandit is Python-only, single-file
  and fast, so it belongs in pre-commit. Semgrep adds interprocedural taint
  analysis and a rule language, which is the only practical way to mechanically
  enforce this repo's own invariants (matching must not read compensation; PII
  must not reach a logger; a clinical field must not default to zero). Semgrep
  is **not yet adopted**; those four rules are the next security increment.
- **osv-scanner over pip-audit and safety.** It parses `uv.lock` natively, so
  there is no `requirements.txt` export to drift. `safety` was rejected: it
  moved to an account/API-key model with a commercial database, which is a poor
  fit for a project whose purpose includes minimizing external data flow.
- **`uv audit` is the likely future replacement** for osv-scanner here (uv-native,
  4-10x faster, and `malware-check` aborts an install *before* a malicious
  package's hooks run). It is gated behind a preview feature and needs a newer
  uv than the 0.7.2 pinned on the current dev machine. Revisit after upgrading.
- **gitleaks over trufflehog and detect-secrets.** Its TOML rule format lets the
  Iranian PII patterns live in the same engine, with the same `--redact`
  guarantee, over both staged changes and full history. detect-secrets needs a
  packaged Python plugin for custom detectors and its baseline file becomes a
  perpetual merge-conflict tax.
- **Reports are always redacted.** A scan report containing the PII it found,
  uploaded as a CI artifact, is a worse leak than the commit that triggered it.
