# Synthetic Telegram export fixture

Entirely fabricated. Contains no real person, phone number, national ID,
medical value or image. Modelled on the DOM documented in
`docs/ingestion/TELEGRAM_HTML_EXPORT_STRUCTURE.md`.

Deliberate cases:
- `message-1`, `message-2`: service date dividers with NEGATIVE ids
- `message101`: normal text-only
- `message102`: joined - no `from_name`, sender must carry forward
- `message103`: photo whose original IS present
- `message104`: photo whose original is ABSENT, thumbnail only
- `message105`: same-file reply with onclick
- `message106`: forwarded - current poster and original author differ
- `message107`: document that was not exported (div, not anchor)
- `message108`: pre-2022 timestamp with no UTC offset
- `message109`: username and telephone links - unverified contact evidence
- `messages2.html`: cross-file reply, no onclick
