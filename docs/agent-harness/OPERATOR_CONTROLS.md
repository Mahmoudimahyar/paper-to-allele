# Operator controls and enforcement

P1 of `HARNESS_READINESS_REVIEW_2026-09-01.md`. Instructions are context, not
enforcement; these mechanisms are enforcement. Everything here is verified by
`tests/contracts/test_hooks.py`.

## 1. Halting a run — `AGENT_STOP`

```bash
echo "why you are stopping it" > AGENT_STOP
```

Every subsequent tool call is blocked until a human deletes the file. The
contents are optional and are shown to the agent. The agent is instructed not to
delete it and is blocked from doing so, because the guard runs before the tool
call that would remove it. **Recovery is a human filesystem action:**

```bash
rm AGENT_STOP
```

Note the limits: this halts *tool calls*, not the session. The model can still
emit text, and the `Stop` hook still runs its checkpoint commit.

## 2. Redirecting a run — `STEER.md`

```bash
echo "stop gold-plating the parser, move to HIST-002" > STEER.md
```

The next tool call is blocked, the message is delivered to the agent, and the
file is truncated so it is delivered exactly once. An empty file delivers
nothing (`touch STEER.md` is a no-op).

`STEER.md` is a convenience channel, **not a trust boundary**: an agent with
write access can author its own steering message. Never route anything
security-relevant through it.

Both files are gitignored; they are runtime state, not repository content.

## 3. Hooks

| Event | Matcher | Script | Purpose |
|---|---|---|---|
| `PreToolUse` | `*` | `guard_session.sh` | kill switch, then one-shot steering |
| `PreToolUse` | `Edit\|Write\|Bash` | `guard_ledger.sh` → `.py` | protect the acceptance ledger |
| `PostToolUse` | `Edit\|Write` | `post_edit_check.sh` | ruff fix + format the touched file |
| `Stop` | — | `stop_checkpoint.sh` | commit a WIP checkpoint |
| `SessionStart` | — | `session_start.sh` | orientation, printed into context |

Design decisions worth keeping:

- **Blocking is `exit 2` + stderr, never JSON.** Malformed JSON on stdout is a
  *non-blocking* error: the tool call proceeds. A guard that fails open when its
  output is malformed is worse than no guard. `exit 2` blocks unconditionally
  and stderr becomes the reason. Note `exit 1` does **not** block.
- **The ledger guard also matches `Bash`.** The upstream reference guards only
  `Write`/`Edit`, so `sed -i`, `jq`, or a `python -c` one-liner rewrites the
  contract file unchecked. Reads stay allowed; only mutations are blocked.
- **Missing Python fails closed.** The reference hardcodes `python3`, which
  frequently does not exist on Windows, and its gate then silently no-ops.
- **`Stop` never blocks.** A blocking `Stop` hook is overridden after 8
  consecutive blocks, silently turning the gate into a no-op. It also has no
  matcher support — one added there is ignored.
- **Path translation is explicit** (`scripts/hooks/_paths.sh`). `CLAUDE_PROJECT_DIR`
  is a native path (`C:\...`) while hooks run under Git Bash (`/c/...`), and
  `cygpath` is not always present. Without this the kill switch silently never
  fires on Windows.

### Verifying hooks are live

Hooks load at session start, so changes need a new session. To confirm:

```bash
echo "verifying the operator channel" > STEER.md
```

Then have the agent run any command. It should be blocked and shown the message,
and `STEER.md` should be 0 bytes afterwards. `tests/contracts/test_hooks.py`
covers the logic; this confirms the wiring.

## 4. Permissions

`.claude/settings.json` allow-lists the commands an autonomous run needs
(`uv run`, `pytest`, `ruff`, `mypy`, `python scripts/*`, read-only git plus
`add`/`commit`) so the agent does not stall on prompts, and denies the
safety boundary: `.env`, `data/raw/**`, `data/gold/**`, `data/review/**`, and
`curl`/`wget` egress. `git push`, `gh`, `docker`, `rm -rf`, and edits to
`.claude/settings.json` itself are set to **ask**, so an unattended run stops
rather than widening its own permissions.

Three syntax traps, each covered by a test:

- Only `Edit(path)` and `Read(path)` are consulted for file rules. A
  `Write(...)`, `Glob(...)`, or `MultiEdit(...)` path rule is accepted, never
  applied, and warned about at startup.
- Bash rules match the whole command; `Bash(git status*)` also matches
  `git statusfoo`. The canonical form is `Bash(git status:*)`.
- Precedence is deny → ask → allow across every settings scope, and specificity
  does not matter. A broad deny cannot carry allow-list exceptions.

Project `allow` rules only apply after the workspace trust dialog is accepted,
so the first session in a fresh clone still prompts once.

## 5. What is deliberately NOT enforced

- An agent with shell access can defeat any of this. These controls stop
  *drift and self-certification*, not a determined bypass.
- The evidence requirement checks that a file exists and is non-empty; it does
  not verify that the evidence supports the criterion. That judgment is what the
  independent reviewer pass is for.
