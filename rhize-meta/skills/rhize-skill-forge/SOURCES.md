# Rhize Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision. Format mirrors `record_provenance.py`; the
`--check-drift` flag parses these blocks. See `references/provenance.md` for the field spec and
`references/drift-boundaries.md` for how drift detection is divided across systems.

## skill-creator — 2026-06-15
- **Source:** Anthropic example skills (installed as `example-skills:skill-creator` / `anthropic-skills:skill-creator`)
- **Upstream ref:** bundled with the example-skills marketplace (version tracked by the `ai-stack-version-drift` sensor)
- **License:** Anthropic example skill — verify at source before copying (DEFER copies nothing, so moot here)
- **Verb:** DEFER
- **Target:** rhize-skill-forge (Step 5 eval loop), skill-refinement
- **Took:** nothing — used as-is for the eval/verify loop
- **Verified:** n/a (DEFER)
- **Drift check:** `# ai-stack-version-drift reports example-skills bumps; re-check the eval-loop API if it moves`
- **Notes:** Canonical "build a skill from scratch + eval" engine. Forge and skill-refinement defer to it rather than reimplementing. First ledger entry — demonstrates the format and un-inerts `--check-drift`.
