# Agent autonomy policy

## Agents may do without asking
- read repo-local docs/code/tests;
- create/edit local code, tests, docs, migrations and synthetic fixtures for the active task;
- run local tests, linters, OCR benchmarks on approved local data paths, and disposable local databases;
- create branches/worktrees/commits when the human workflow allows;
- refactor within the active spec when behavior remains covered by tests;
- add a human-action request without stopping unrelated work.

## Ask a human only when required
- secret/API credential or external access grant;
- choosing among conflicting product/clinical/legal requirements;
- destructive action against non-disposable data;
- deployment/publish/production migration or data disclosure;
- external account purchase/contract;
- decision that materially changes clinical policy or intended use.

## Never do autonomously
- fabricate credentials or medical values;
- upload real historical health data to an unapproved cloud service;
- contact historical donors/recipients;
- publicly expose historical profiles;
- weaken clinical/security gates to unblock a task;
- deploy or destroy production data merely because tests pass.

The goal is **low-friction local autonomy with narrow human gates**, not constant permission-seeking and not unbounded external power.
