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
| `PreToolUse` | `Edit\|Write\|Bash\|PowerShell\|NotebookEdit` | `guard_ledger.sh` → `.py` | protect the contract files |
| `PostToolUse` | `Edit\|Write` | `post_edit_check.sh` | ruff fix + format the touched file |
| `Stop` | — | `stop_checkpoint.sh` | commit a WIP checkpoint |
| `SessionStart` | — | `session_start.sh` | orientation, printed into context |

Design decisions worth keeping:

- **Blocking is `exit 2` + stderr, never JSON.** Malformed JSON on stdout is a
  *non-blocking* error: the tool call proceeds. A guard that fails open when its
  output is malformed is worse than no guard. `exit 2` blocks unconditionally
  and stderr becomes the reason. Note `exit 1` does **not** block.
- **Two contract files are protected, not one.** `acceptance.json` holds the
  criteria; `WORK_QUEUE.json` holds the `status` field the gate protects.
  Guarding only the ledger left the gate optional — an agent could edit the
  queue directly and set `COMPLETE` without ever invoking `taskctl`.
- **The guard matches shells, not just editors.** The upstream reference guards
  only `Write`/`Edit`, so `sed -i`, `jq`, or a `python -c` one-liner rewrites the
  contract file unchecked. `PowerShell` is included because it takes a `command`
  exactly like `Bash`. Reads stay allowed; only writes are blocked, and redirect
  *direction* is read — `cat ledger > backup` writes the backup, not the ledger.
- **`--force` is recorded, not just announced.** `taskctl set … COMPLETE --force`
  requires `--reason` and writes a `forced_complete` entry into the queue, so the
  override survives the session and appears in review and `git log`.
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

## 5. Recovering from a locked-out session

`guard_ledger.sh` fails closed: if `guard_ledger.py` is missing it blocks every
`Edit`, `Write`, `Bash`, `PowerShell`, and `NotebookEdit` call. That is correct,
but it means **deleting the guard deadlocks the agent**, including the call that
would restore it. This happened during development.

Recovery is a human action from a normal terminal:

```bash
git checkout -- scripts/hooks/guard_ledger.py
```

The same applies to `AGENT_STOP`: recovery is `rm AGENT_STOP` by a human.

## 6. What is deliberately NOT enforced

Stated plainly, because a control that is documented as stronger than it is will
be trusted more than it deserves.

- **An agent that can write and run scripts can reach the ledger.**
  `Edit(scripts/**)` and `Bash(uv run:*)` are both allowed, so an agent can
  author a script that rewrites `acceptance.json` and run it; the hook inspects
  the command text, not what the script does. This is *not* closable by
  permissions while the agent still needs to run project code. The durable
  protection is that **`taskctl` re-runs the acceptance commands at COMPLETE
  time and does not trust the ledger's contents** — a forged ledger still cannot
  produce a passing test run.
- **A tautological test passes the gate.** Nothing mechanical distinguishes a
  test that proves a criterion from one that asserts `True`. `spec_lint` can
  enforce that a criterion is *claimed*; only the independent reviewer pass
  (`km-review`) can judge whether it is *earned*.
- **An agent can shrink the definition of done** by deleting acceptance bullets
  from a spec: `spec_lint` checks that every criterion is owned, not that the
  set has not shrunk. Spec edits belong in review.
- **The evidence check verifies a passing run of that task, not that the run
  demonstrates the criterion.** It rejects a failed run, an empty file, and
  another task's log; it cannot tell you the test was meaningful.
- `STEER.md` is not a trust boundary (see §2).

These are the reasons the review discipline in `AGENTS.md` is not optional. The
harness stops *drift and self-certification*; it does not replace a reviewer.
