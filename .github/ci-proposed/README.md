# CI proposals

`.github/workflows/` is protected (the `protect-files.sh` hook blocks agent edits), so any new or
changed workflow is drafted here first and promoted by a maintainer with `git mv` into
`.github/workflows/`.

**Promoted so far:** `validate.yml` on 2026-09-03 — the gate mirroring the local release
contracts `scripts/bump_version.py`'s `REPOSITORY_CONTRACTS` runs on every version bump (pytest,
plugin manifest validation, config lint, Dev Flow doctor, skill-map freshness, setup-artifacts
freshness, idempotent docs render). It now runs on every push and pull request; see its run history
under Actions. **Pending promotion:** `validate.yml` (2026-09-04) — fixes the per-plugin validation step, whose
`[ -f … ] && …` loop returned the last non-plugin directory's test status and failed the run after every
plugin had passed (run 33878608873); also points the setup-artifacts check at `rhize-core/` and drops
the stale "not live" header. Promote with:

```bash
git mv -f .github/ci-proposed/validate.yml .github/workflows/validate.yml
```
