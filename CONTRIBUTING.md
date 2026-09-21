# Contributing

Thanks for your interest. This project handles a domain where a wrong value is a
clinical hazard, so the contribution process is stricter than most. The rules
below are the same ones the maintainers and the AI coding agents work under;
the agent-facing version is [`AGENTS.md`](AGENTS.md).

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## The one rule that outranks the others

**Never commit real personal or medical data.** No identities, phone numbers,
national IDs, lab report images, chat exports, OCR crops, label files, or logs
and screenshots containing any of them. Tests use synthetic fixtures only. If
you find such data anywhere in the repository, follow
[`SECURITY.md`](SECURITY.md) and do not open a public issue.

## Development setup

You need [uv](https://github.com/astral-sh/uv) and Python 3.12.

```bash
git clone https://github.com/mahmoudimahyar/paper-to-allele.git
cd paper-to-allele
uv sync --frozen --extra hist --extra hla --extra image --extra ocr
uv run --frozen python scripts/doctor.py
pre-commit install   # optional, runs the fast checks on commit
```

`--frozen` is deliberate: a stale `uv.lock` fails loudly instead of silently
re-resolving. If you change dependencies, update the lockfile in the same
change and record the addition in the OSS register.

## The gate

One command decides whether a change is acceptable, locally and in CI:

```bash
uv run --frozen python scripts/verify_repo.py
```

It runs 12 steps, none skippable: the documentation, spec, architecture and
invariant lints, the PII scan, `ruff check`, `ruff format --check`, strict
`mypy`, Bandit, the full test suite, and a 100% coverage floor on the core
modules. CI calls the same script, so a local pass means a CI pass.

Faster loops while you work: `just lint`, `just types`, `just unit`.

## Change workflow

1. **Open an issue first** for anything beyond a small fix, so the approach can
   be agreed before you invest in it.
2. **Write the failing test first.** This is mandatory for domain, security,
   ingestion, OCR and matching rules.
3. **Make the smallest coherent change** that satisfies the spec. Prefer an
   existing capability over a new dependency.
4. **Run the gate.**
5. **Open a pull request** using the template. High-risk changes (matching,
   HLA, OCR acceptance, anything touching document access) get a separate
   sceptical review that looks for counterexamples and missing tests.

### What will get a change rejected

- Weakening or deleting a test to get green, unless a versioned spec or policy
  changed and the PR says so.
- Coercing a missing clinical value to zero, compatible, or a default.
- Inferring high-resolution HLA from low-resolution typing.
- Assigning a locus from OCR text alone, outside the three documented
  exceptions.
- A decision pass that cannot be dry-run and undone.
- A number in a document that no script can reproduce.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/), with a scope:

```text
feat(ocr): ...      fix(matching): ...      test(hla): ...
docs(ingestion): ... refactor(review): ...  chore(ci): ...
```

Write the body for the person debugging this in a year: what was wrong, why,
and how you know it is fixed. The history of this repository keeps its mistakes
on purpose; a commit that says "I was wrong about X, here is the evidence" is
welcome.

## Branches

Trunk-based. Branch from `main`, keep pull requests small and single-purpose,
and rebase rather than merge `main` into your branch. One task per branch.

## Documentation

- Durable facts belong in code, specs, ADRs and docs, not in chat or PR threads.
- Architectural decisions get an ADR in
  [`docs/architecture/decisions/`](docs/architecture/decisions/).
- Measurements get a dated report and a script that reproduces them.
- Things that are known to be wrong and not yet fixed go in
  [`docs/agent-memory/KNOWN_ISSUES.md`](docs/agent-memory/KNOWN_ISSUES.md),
  stated plainly.

## Questions

Open a [discussion or issue](https://github.com/mahmoudimahyar/paper-to-allele/issues).
For anything involving security or personal data, use
[`SECURITY.md`](SECURITY.md) instead.
