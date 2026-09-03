# Telegram Desktop HTML export — DOM reference

Source of truth for HIST-001. Every claim here was taken from the generator
itself, `Telegram/SourceFiles/export/output/export_output_html.cpp` in
`telegramdesktop/tdesktop`, and cross-checked against a real modern export and
three independent third-party parsers.

Recorded so that no future session re-derives it, and so synthetic fixtures can
be faithful without any real archive present.

## Message wrapper

```html
<div class="message default clearfix" id="message1301549">
```

Attribute order is always alphabetical (`class` before `id`) because the
generator serialises a `std::map`. Message id is `message<ID>`.

## Joined messages — the structural trap

```html
<div class="message default clearfix joined" id="message1301552">
```

A joined message **omits both the `pull_left userpic_wrap` block and the
`from_name` block entirely**. Its `body` starts directly with the date div.

That is the single most important fact for the parser: **a joined message
carries no sender at all**, so the sender must be carried forward from the
previous non-joined message. Reading "no from_name" as "unknown sender" would
silently orphan large parts of the archive.

The generator joins a message to the previous one only when *all* hold
(`messageNeedsWrap`, inverted):

- a previous message exists and is a normal (not service) message;
- same `fromId`;
- same `viaBotId`;
- same calendar date;
- identical forwarded state;
- within `kJoinWithinSeconds = 900` seconds (1 second when forwarded).

A service message always breaks the chain.

**This is a display grouping, not a semantic one.** Two unrelated ads posted by
the same person 14 minutes apart are "joined". `HIST-002` must not treat joining
as evidence that two messages describe the same candidate.

## Timestamps

```html
<div class="pull_right date details" title="03.12.2025 19:07:28 UTC+02:00">
19:07
</div>
```

The `title` attribute carries the full timestamp; the element text is only
`HH:MM`. The `UTC±HH:MM` suffix was added between tdesktop v3.7.3 and v3.7.6
(2022); older exports read `title="11.02.2020 09:03:59"` with no zone. Fixtures
cover both, because the archive predates the change.

## Forwarded

**Corrected 2026-09-03 against the real archive (66,991 forwarded messages).**
The forwarded block is nested **inside** the message's own `body`, which carries
the current poster's `from_name` and the posting date:

```html
<div class="pull_left userpic_wrap">…</div>
<div class="body">
 <div class="pull_right date details" title="14.01.2026 00:25:11 UTC+02:00">00:25</div>
 <div class="from_name">
Current Poster
 </div>
 <div class="pull_left forwarded userpic_wrap">…</div>
 <div class="forwarded body">
  <div class="from_name">
Original Sender <span class="date details" title="14.01.2026 00:22:03 UTC+02:00"> 14.01.2026 00:22:03</span>
  </div>
  <div class="text">…</div>
 </div>
</div>
```

An earlier revision of this file showed only the inner two elements, and a
parser written from it replaced the message body with the forwarded block. That
loses the current poster on **every** forwarded message — 37% of this archive —
and silently attributes each one to whoever posted previously. The nesting is
the part that matters.

The forwarded block carries the *original* author and date; its `text` and
`media_wrap` are the message's content. The enclosing `body` carries the
*current* poster and the time it was posted here. Per the product constitution
these are different identities and must stay separate fields.

`class="forwarded"` also matches the avatar column
`pull_left forwarded userpic_wrap`, so selecting the forwarded body requires
**both** `forwarded` and `body`.

## Reply

```html
<div class="reply_to details">
In reply to <a href="#go_to_message1301549" onclick="return GoToMessage(1301549)">this message</a>
</div>
```

The target id appears twice (href fragment and onclick). A cross-file reply gets
a filename prefix and **no** `onclick`; a cross-chat reply has no link at all.

## Media

Two entirely different shapes, and conflating them is the main parsing hazard.

**File present** — dedicated wrapper with a sized `<img>`:

```html
<div class="media_wrap clearfix">
 <a class="photo_wrap clearfix pull_left" href="photos/photo_1@03-12-2025_19-08-10.jpg">
  <img class="photo" src="photos/photo_1@03-12-2025_19-08-10_thumb.jpg" style="width: 260px; height: 195px"/>
 </a>
</div>
```

**File absent, or no raster thumb possible** (documents, voice, round video,
animated `.tgs` stickers) — the generic block, where the outer element is a
`<div>` rather than an `<a>` when there is no link:

```html
<div class="media_wrap clearfix">
 <div class="media clearfix pull_left media_file">
  <div class="fill pull_left"></div>
  <div class="body">
   <div class="title bold">…</div>
   <div class="description">Not included, change data exporting settings to download.</div>
  </div>
 </div>
</div>
```

A missing file is signalled by `div.description` holding exactly one of:

- `Unavailable, please try again later.`
- `Exceeds maximum size, change data exporting settings to download.`
- `Not included, change data exporting settings to download.`

### Thumbnail naming differs by media kind

- **Photos and stickers**: `_thumb` is inserted *before the first dot after the
  last slash* — `photo_1@…-10.jpg` → `photo_1@…-10_thumb.jpg`.
- **Documents** (video, files, round video): `_thumb.jpg` is appended to the
  *whole* filename, extension included — `video_1.mp4` → `video_1.mp4_thumb.jpg`.

Media subfolders: `photos`, `video_files`, `animations`, `stickers`,
`voice_messages`, `round_video_messages`, `files`.

## Service messages and date dividers

```html
<div class="message service" id="message-1">
 <div class="body details">
3 December 2025
 </div>
</div>
```

No `default`, no `clearfix`; body is `body details`. **Date dividers carry
negative, monotonically decreasing ids** (`message-1`, `message-2`, …) that are
not Telegram message ids at all. Real service actions reuse the true positive
id. A parser that treats `id` as a message id without checking the sign will
invent messages.

Divider text is `D Month YYYY` in English, day not zero-padded.

## File layout

`kMessagesInFile = 1000`. Files are `messages.html`, `messages2.html`,
`messages3.html` … (the first has no number). Pages link with
`<a class="pagination block_link" href="…">` carrying "Next messages" and
"Previous messages".

## Whitespace

Block tags emit a newline plus depth-proportional indentation; **text content is
emitted at column 0** with no indentation. Void tags close as `<img …/>`. Do not
write a parser that relies on indentation to find text.

## Sources

- `telegramdesktop/tdesktop` — `export_output_html.cpp`, `export_data_types.cpp`
- A complete real export fixture (`EmerickGrimm/Telegram-Chat-Export-Reader`)
- Selectors in `craftamap/telegram-export-parser` and
  `gabekanegae/telegram-export-converter`
- The export's own shipped `css/style.css`, which defines `.default.joined`
