# Local data directory — never commit real records

Expected local layout (all real files are gitignored):

```text
data/
  raw/telegram-export/      # immutable HTML/JSON/media supplied by human
  derived/inventory/
  derived/dedupe/
  derived/ocr/
  review/
  gold/
  golden/                   # only synthetic/de-identified approved fixtures may be committed
```

The repository ships no real donor/recipient data. Production/sensitive historical inputs must remain outside Git and must not be pasted into coding-agent prompts unnecessarily.
