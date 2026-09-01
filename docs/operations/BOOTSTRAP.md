# Local bootstrap

Recommended:
```bash
uv sync --extra dev
python scripts/doctor.py
python scripts/verify_repo.py
```

For MVP-HIST parsing later:
```bash
uv sync --extra dev --extra hist --extra image --extra hla
```

OCR is intentionally a separate environment spike because Paddle/PaddlePaddle/Tesseract behavior is platform-sensitive. Do not block HIST-001 on OCR installation.

PostgreSQL:
```bash
docker compose up -d postgres
```

The first real-data run additionally needs `KM_TELEGRAM_EXPORT_DIR` in local `.env`; synthetic tests do not.
