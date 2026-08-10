# Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision.

**Upstreams repointed remote 2026-08-10:** the local marketplace-cache paths below (context-engineering-marketplace, since uninstalled) were replaced with raw.githubusercontent.com URLs against the identified upstream, `muratcankoylan/Agent-Skills-for-Context-Engineering` (default branch `main`), so drift checking works from any machine rather than only one with that marketplace still installed. Each URL was verified with `curl` (HTTP 200 + real SKILL.md frontmatter) before being recorded.

## context-fundamentals — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/context-fundamentals/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for context-fundamentals`
- **Notes:** gate: safety=pass, overlap nearest=context-engineering (0.052)

## context-degradation — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/context-degradation/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for context-degradation`
- **Notes:** gate: safety=pass, overlap nearest=context-fundamentals (0.124)

## context-compression — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/context-compression/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for context-compression`
- **Notes:** gate: safety=pass, overlap nearest=context-fundamentals (0.136)

## context-optimization — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/context-optimization/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for context-optimization`
- **Notes:** gate: safety=pass, overlap nearest=context-fundamentals (0.078)

## memory-systems — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/memory-systems/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for memory-systems`
- **Notes:** gate: safety=pass, overlap nearest=context-compression (0.115)

## filesystem-context — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/filesystem-context/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for filesystem-context`
- **Notes:** gate: safety=pass, overlap nearest=memory-systems (0.198)

## tool-design — 2026-07-20
- **Source:** https://raw.githubusercontent.com/muratcankoylan/Agent-Skills-for-Context-Engineering/main/skills/tool-design/SKILL.md
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for tool-design`
- **Notes:** gate: safety=pass, overlap nearest=context-fundamentals (0.069)

## iterative-retrieval — 2026-07-20
- **Source:** /Users/jamesdeola/.claude/plugins/marketplaces/everything-claude-code/skills/iterative-retrieval
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for iterative-retrieval`
- **Notes:** gate: safety=pass, overlap nearest=context-optimization (0.131)
- **RETIRED 2026-07-28:** removed from this plugin. `ecc@everything-claude-code` is enabled and ships this skill, so the copy was a duplicate that competed for the same invocations — content identical to upstream except frontmatter indentation. Per the marketplace curation rule, Rhize skills close gaps in proven plugins rather than re-shipping them; upstream now owns this outright.

## strategic-compact — 2026-07-20
- **Source:** /Users/jamesdeola/.claude/plugins/marketplaces/everything-claude-code/skills/strategic-compact
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for strategic-compact`
- **Notes:** gate: safety=pass, overlap nearest=context-compression (0.134)
- **RETIRED 2026-07-28:** removed from this plugin. `ecc@everything-claude-code` is enabled and ships this skill, so the copy was a duplicate that competed for the same invocations — fork had DRIFTED BEHIND upstream — ecc 2.0.0 gained a context-size primary signal with window-scaled thresholds (160k/200k, 250k/1M) and COMPACT_CONTEXT_THRESHOLD/INTERVAL; this copy still had the old tool-count-only logic. Per the marketplace curation rule, Rhize skills close gaps in proven plugins rather than re-shipping them; upstream now owns this outright.

## context-budget — 2026-07-20
- **Source:** /Users/jamesdeola/.claude/plugins/marketplaces/everything-claude-code/skills/context-budget
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for context-budget`
- **Notes:** gate: safety=pass, overlap nearest=context-fundamentals (0.065)
- **RETIRED 2026-07-28:** removed from this plugin. `ecc@everything-claude-code` is enabled and ships this skill, so the copy was a duplicate that competed for the same invocations — content identical to upstream except frontmatter indentation. Per the marketplace curation rule, Rhize skills close gaps in proven plugins rather than re-shipping them; upstream now owns this outright.

## token-budget-advisor — 2026-07-20
- **Source:** /Users/jamesdeola/.claude/plugins/marketplaces/everything-claude-code/skills/token-budget-advisor
- **Upstream ref:** n/a
- **License:** NONE STATED
- **Verb:** DEFER
- **Target:** /Users/jamesdeola/dev-local/RHIZE/rhize-plugins/rhize-context-manager/skills
- **Took:** installed as-is (1 skill dir)
- **Verified:** n/a
- **Drift check:** `# define how to detect upstream change for token-budget-advisor`
- **Notes:** gate: safety=pass, overlap nearest=context-engineering (0.032)
- **RETIRED 2026-07-28:** removed from this plugin. `ecc@everything-claude-code` is enabled and ships this skill, so the copy was a duplicate that competed for the same invocations — content identical to upstream except frontmatter indentation. Per the marketplace curation rule, Rhize skills close gaps in proven plugins rather than re-shipping them; upstream now owns this outright.
