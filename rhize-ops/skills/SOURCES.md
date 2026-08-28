# Rhize Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision.

## parallel-agent-optimization — 2026-08-27
- **Source:** https://github.com/affaan-m/ECC/tree/main/skills/parallel-execution-optimizer
- **Additional source:** https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents
- **Upstream ref:** ECC 2.2.0; Superpowers 6.3.0
- **License:** MIT (both upstream plugins)
- **Verb:** DEFER
- **Graph relation:** consumes
- **Target:** rhize-ops:parallel-agent-optimization
- **Took:** nothing copied; wrapper consumes two maintained resources
- **Verified:** Forge safety and overlap scans; 24-run smoke; receipt, graph, and repository tests
- **Drift check:** `use existing ai-stack-version-drift sensor; rerun evals/parallel-agent-skills on movement`
- **Notes:** DEFER+wrap approved 2026-08-27. Second source: https://github.com/obra/superpowers/tree/main/skills/dispatching-parallel-agents. Rhize owns only safety, routing, and evidence contracts.
