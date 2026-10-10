# Skill Forge — Provenance Ledger

One entry per external-skill ingestion decision owned by Project Launcher.

## rhize-visual-plan — 2026-06-25
- **Source:** https://raw.githubusercontent.com/BuilderIO/skills/main/skills/visual-plan/SKILL.md
- **Upstream ref:** `6294124fdb96fb3cf4726c78ea505e4d3a7af00e` (BuilderIO/skills, 2026-06-24)
- **License:** MIT — Copyright (c) 2026 Builder.io (https://github.com/BuilderIO/skills/blob/main/LICENSE)
- **Verb:** FORK
- **Graph relation:** fork-of
- **Target:** project-launcher/skills/rhize-visual-plan
- **Took:** the planning discipline (plan as approval gate, lead with reuse, decide hard-to-reverse bets first, self-review before handoff, visual-surface choice) and the wireframe/canvas/document quality bars, re-skinned to the Rhize stack. The `plan.mdx` format, renderer, Obsidian shell and canvas export are original to Rhize; the hosted Plan UI, `@agent-native` connector and localhost bridge were not taken.
- **Verified:** 2026-10-10 — the pinned commit exists in github.com/BuilderIO/skills and its `skills/visual-plan/SKILL.md` hashes to the baseline below; the Source URL returns HTTP 200 with that skill's frontmatter.
- **Drift check:** `compare upstream skills/visual-plan/SKILL.md on main with the recorded baseline; review the diff by hand before re-baselining or porting anything`
- **Upstream baseline:** sha256:0ea94674b21ea75caa1e64a9944d04fb3d5488ce1e25cc2315d616b685bbaa68 (recorded 2026-10-10)
- **Notes:** Detailed attribution (what was taken, what is original, what was removed, and the secondary MIT `ddunnock/mdx-support` pattern adaptation for `obsidian-plugin/`) lives in the skill-local [`rhize-visual-plan/SOURCES.md`](rhize-visual-plan/SOURCES.md). The baseline is the hash of the upstream SKILL.md at the pinned ingestion commit, not at today's `main`; upstream has moved since then, so the first drift check is expected to report movement for review. No `metadata.rhize.extends`: the skill deliberately does not layer on any in-repo skill (it scopes itself away from `project-launcher`'s PRD pipeline), and the upstream is not a skill-map node an `extends` edge could target.
