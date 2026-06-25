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

## visual-plan (FORK → rhize-visual-plan) — 2026-06-25
- **Source:** https://github.com/BuilderIO/skills/tree/main/skills/visual-plan
- **Upstream ref:** git 6294124 (2026-06-24)
- **License:** MIT (permissive)
- **Verb:** FORK
- **Target:** rhize-visual-plan
- **Took:** Forked the planning methodology + wireframe/canvas/document-quality bars; built an ORIGINAL Rhize MDX plan format (plan.mdx component vocab) + Next.js/Vercel viewer + Obsidian/json-canvas fallback. No @agent-native/hosted-Plan runtime.
- **Verified:** esbuild clean on both .tsx templates; Opus adversarial review = BEATS BASELINE after reconciling a split --wf-* token/surface vocabulary across renderer+docs (fixed).
- **Drift check:** `git ls-remote https://github.com/BuilderIO/skills.git HEAD  # compare to 6294124fdb96fb3cf4726c78ea505e4d3a7af00e`
- **Notes:** ABSORB+FORK per user gate. Lives in project-launcher plugin (skills/rhize-visual-plan). Methodology shared with project-launcher via references/plan-discipline.md.

## visual-plan (ABSORB → project-launcher) — 2026-06-25
- **Source:** https://github.com/BuilderIO/skills/tree/main/skills/visual-plan
- **Upstream ref:** git 6294124 (2026-06-24)
- **License:** MIT (permissive)
- **Verb:** ABSORB
- **Target:** project-launcher
- **Took:** Plan-discipline methodology -> project-launcher/skills/project-launcher/references/plan-discipline.md + Phase-3 'Writing the PRD' & Obsidian-Integration pointers + tracked SKILL.patch.md.
- **Verified:** Pointers resolve to real files; Opus review confirms genuine value, no wholesale duplication of the FORK.
- **Drift check:** `git ls-remote https://github.com/BuilderIO/skills.git HEAD  # compare to 6294124fdb96fb3cf4726c78ea505e4d3a7af00e`
- **Notes:** Companion to the FORK. project-launcher plugin bumped 1.3.0 -> 1.4.0; marketplace 1.8.1 -> 1.9.0.
