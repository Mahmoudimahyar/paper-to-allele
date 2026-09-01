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
| Primary Persian OCR | PaddleOCR PP-OCRv5 Arabic recognizer | ADOPT after golden benchmark |
| Second OCR | Tesseract 5 (`fas`, `eng`) | ADOPT as second opinion |
| VLM fallback | PaddleOCR-VL | ADOPT after resource/accuracy benchmark |
| OCR alternative | Surya | BENCHMARK, not mandatory |
| HLA nomenclature | py-ard | ADOPT with pinned IPD release and license review |
| Fuzzy text | RapidFuzz | ADOPT |
| Perceptual hashing | imagehash or `perception` | SPIKE then pin one |
| Testing | pytest, Hypothesis, pytest-bdd | ADOPT |
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
