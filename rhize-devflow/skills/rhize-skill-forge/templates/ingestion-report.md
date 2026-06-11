# Ingestion Report — <candidate-name>

> Fill one of these per candidate. Keep it; it makes the next ingestion faster and feeds the ledger.

## 1. Profile
- **Source:** <url / path / marketplace name>
- **Version / ref:** <version | git commit>
- **License:** <SPDX> → class: <permissive | attribution | copyleft | none | restrictive>
- **Frontmatter valid:** <yes/no>
- **Size / structure:** <N lines, M headers>
- **Resources:** <scripts:N references:N commands:N hooks:N ...>
- **MCP / external deps:** <list or none>

## 2. Overlap
- **Nearest Rhize skill:** <name> (score <0–1>)
- **Full ranking:** <top 3>
- **Heuristic verb:** <from overlap_scan>
- **My read after opening both:** <agree / override, and why>

## 3. Decision
- **Verb:** <DEFER | ABSORB | FORK | REJECT | WATCH>
- **Worth taking:** <specific files / patterns, or "nothing">
- **Leaving behind:** <what and why>
- **Target skill (if ABSORB):** <rhize-skill> via <SKILL.patch.md | SKILL.extend.md | new reference>
- **License gate:** <clear | needs attribution | escalated to user>

## 4. Execution
- **What was done:** <patch applied / forked to rhize-X / pointer added / rejected>
- **Attribution kept:** <where>

## 5. Verification (required for ABSORB/FORK)
- **Eval prompts used:** <2–3 realistic prompts>
- **With-skill vs baseline:** <result>
- **Verdict:** <beats baseline → keep | does not → revert and re-scope>

## 6. Provenance
- **Ledger entry written:** <yes — SOURCES.md>
- **Vault note:** <path>
- **Drift check command:** <command>
