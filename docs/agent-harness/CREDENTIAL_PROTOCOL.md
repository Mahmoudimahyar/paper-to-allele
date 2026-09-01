# Credential and human-action protocol

## Principle
Agents may detect and request credentials; they may never fabricate, infer, search for, log, print, or commit secret values.

## Procedure
1. Run `python scripts/doctor.py` (or `--json`).
2. If an entry required by the current phase/task is missing, emit exactly one concise request:
   `HUMAN ACTION REQUIRED [ID]: <what to provide/do> — <why> — expected env var/config name.`
3. Add/update the same item in `docs/agent-memory/HUMAN_ACTIONS.md` without the secret value.
4. Continue all independent tasks instead of blocking the whole session when possible.
5. Once the human sets the secret in `.env`/secret store, validate presence/shape without echoing it.

## Allowed human-action categories
- credential/API token;
- access/permission grant;
- external account creation;
- irreversible deployment/destructive action approval;
- legal/clinical/product policy decision that cannot be inferred;
- representative local data path.

## Forbidden behavior
- storing real secret values in repo memory or an execution plan;
- printing token prefixes/suffixes as “proof”;
- putting secrets in command history when a stdin/file secret mechanism is available;
- weakening a test because an external credential is missing;
- asking for later-phase credentials during MVP-HIST.

## Phase rule
MVP-HIST should require **no cloud/API credential**. It needs only local paths and local tooling. Telegram bot credentials are not requested until V2/V3.
