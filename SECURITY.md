# Security and privacy policy

This project processes medical documents. Alongside ordinary software
vulnerabilities, **the exposure of personal or medical data is treated as the
most severe class of issue here**, and is handled the same way.

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting:

1. Go to the [Security tab](https://github.com/mahmoudimahyar/paper-to-allele/security/advisories/new).
2. Choose **Report a vulnerability**.

Please include what you found, where, how to reproduce it, and what you think
the impact is. If the finding involves real personal data, describe its location
rather than pasting the data itself.

**Expected response:** acknowledgement within 7 days, and an assessment with a
plan within 30 days. This is a research project maintained by one person, so
please allow reasonable time before any public disclosure. Reporters are
credited in the fix unless they prefer otherwise.

## In scope

- Personal or medical data found anywhere in the repository or its git history.
- A path by which the pipeline could write such data into a tracked file, a
  log, a test artefact or a CI artefact.
- A way to defeat the privacy scanner, the architecture lint, or the acceptance
  ledger's evidence requirement.
- A defect that could cause a clinically wrong output to be presented as
  reliable: a wrong locus binding, a mismatch count that flatters a pair, a
  blocked pair rendered as rankable, or a missing value treated as compatible.
- Ordinary vulnerabilities in the code or its dependencies.

## Out of scope

- The absence of authentication or transport security in the local review
  tools. They bind to `127.0.0.1`, are served from a local directory, and are
  not intended to be exposed to a network.
- Findings that require an attacker who already has the operator's machine and
  filesystem access.
- Reports from automated scanners with no demonstrated impact.

## How this project defends the data

These are design commitments, and a reachable counterexample to any of them is
a valid report.

- **No real data is in version control.** The archive, every derived database,
  every image crop and every label file live outside the repository and are
  gitignored. The published history was audited before release.
- **The gate scans for it.** `scripts/scan_pii.py` runs in the 12-step
  verification gate and in CI. It has no allow-list by design: a finding must be
  fixed at the source rather than suppressed.
- **Structural isolation.** The matching package cannot import or query
  compensation data; `scripts/architecture_lint.py` enforces it rather than
  relying on convention.
- **Sender identity is hashed** where the pipeline needs only to distinguish one
  poster from another.
- **Secrets live in an ignored `.env`**, never in documents, memory files or
  code. `.env.example` lists names only.

## A note on the review tools

Labels created in the browser review tool live in that browser's local storage
until exported, and exported label files contain medical values. Keep them
outside version control, treat them as you would the source documents, and see
`KI-031` in [`docs/agent-memory/KNOWN_ISSUES.md`](docs/agent-memory/KNOWN_ISSUES.md)
for the known fragility of that path.
