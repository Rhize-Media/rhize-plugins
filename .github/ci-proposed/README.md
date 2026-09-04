# CI proposals

`.github/workflows/` is protected (the `protect-files.sh` hook blocks agent edits), so any new or
changed workflow is drafted here first and promoted by a maintainer with `git mv` into
`.github/workflows/`.

**Promoted so far:** `validate.yml` on 2026-09-03 — the gate mirroring the local release
contracts `scripts/bump_version.py`'s `REPOSITORY_CONTRACTS` runs on every version bump (pytest,
plugin manifest validation, config lint, Dev Flow doctor, skill-map freshness, setup-artifacts
freshness, idempotent docs render). It now runs on every push and pull request; see its run history
under Actions. This directory is empty between proposals.
