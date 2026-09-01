# Ingestion-specific agent rules
- Evidence layer only: do not infer canonical person identity while parsing.
- Current sender, forwarded sender, advertised contact, and medical subject are distinct concepts.
- Parse raw source idempotently; preserve raw text and unknown fragments.
- Explicit Telegram structure outranks adjacency when building bundles.
- No OCR inside the HTML parser.
