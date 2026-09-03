# Proposed CI (not live)

`validate.yml` mirrors the local release contracts `scripts/bump_version.py`'s
`REPOSITORY_CONTRACTS` already runs on every version bump: pytest, plugin
manifest validation, config lint, Dev Flow doctor, skill-map freshness,
setup-artifacts freshness, and an idempotent docs render.

It is a **proposal**, not CI parity — it has never run. `.github/workflows/`
is protected, so a maintainer must install it manually:

```bash
git mv .github/ci-proposed/validate.yml .github/workflows/validate.yml
```

Until then, these checks run only locally at release time.
