# Skill map: coverage follow-ups and viewer forces (2026-10-10)

Impact map for the follow-up to commit `5ff6310` ("broaden relationship/tag coverage and refresh
viewer UI"). It closes every finding from that audit and adds Obsidian-style force controls to the
viewer.

## Current behavior

- **Tag vocabulary:** `catalog/tags.json` has 31 topics and 12 stacks. `docs/skill-map.md` targets ≤25
  topics and ≤10 stacks. Several topics and stacks are single-use near-duplicates.
- **rhize-visual-plan provenance:** it is a documented fork of BuilderIO `visual-plan`, but its
  provenance lives only in the skill-local `project-launcher/skills/rhize-visual-plan/SOURCES.md`.
  The compiler reads only plugin-level `skills/SOURCES.md`, so no `fork-of` edge or drift check exists.
- **Empty conditions:** `condition/test-failure`, `condition/lint-failure` and `condition/merge-conflict`
  have no `remediates` edges, so remediation-suggester never fires for them.
- **Unverified edges:** `parallel-agent-optimization —replaces→` the ECC and Superpowers parallel
  skills is the least-verified pair of edges from the audit.
- **Outreach setup:** `rhize-outreach-setup —precedes→ rhize-outreach-run` lets next-step-suggester
  propose `run` even when `/rhize-core:setup` launched the wizard (`--from-rhize-setup`). rhize-tasks
  already tells its wizard to stop in that case; outreach does not.
- **Releases:** the six plugins with frontmatter edits from `5ff6310` have no version bump or
  CHANGELOG entry yet.
- **Viewer layout:** a single O(n²) repulsion with a hard 500px cutoff, fixed link distance and no
  collision. Dense plugins overlap, and users cannot tune the layout.

## Intended semantic delta

1. **Tag consolidation:** cut topics to ≤25 and stacks to ≤10 by retiring single-use, near-duplicate
   slugs. Remap each carrier skill to the surviving slug; slug names otherwise stay as they are.
   Router and disclosure behavior may shift only for the retired slugs. Tests and docs follow.
2. **Visual-plan fork:** add a `project-launcher/skills/SOURCES.md` ledger entry
   (`Graph relation: fork-of`) for rhize-visual-plan, with upstream URL, ref and drift-check fields.
   The skill-local SOURCES.md stays as the detailed attribution.
3. **Condition remediators:** add `remediates` edges for the three empty conditions only where a
   verified third-party agent or Rhize skill actually fixes that failure. Otherwise leave the
   condition empty and record why.
4. **Parallel-skill edges:** re-verify the two `replaces` edges against `rhize-ops/skills/SOURCES.md`
   and the skill's `references/provenance.md`. Keep or drop each with recorded reasoning.
5. **Outreach setup:** remove the `setup —precedes→ run` edge (`doctor —precedes→ run` stays). Give
   `/rhize-outreach:setup` the same "stop when launched with `--from-rhize-setup`" clause rhize-tasks
   has.
6. **Version bumps:** patch-bump every plugin whose shipped files changed, via
   `scripts/bump_version.py`.
7. **Viewer forces:** Barnes–Hut repulsion without a hard cutoff, collision radius, and adjustable
   center, repel, link-strength and link-distance forces. Add a Forces panel (sliders, reheat, freeze),
   with settings saved per viewer in localStorage. Docs updated.

## Invariants

- **Generated files:** `generated/` is never hand-edited; rebuild with `scripts/build_skill_map.py`.
- **Conditions:** the condition vocabulary stays at exactly 5.
- **Evidence:** every new edge is backed by source text; no `follows` or `usage-cooccurs` edges are
  fabricated.
- **Static map:** contains only `origin: rhize` nodes.
- **Viewer data:** the viewer template keeps the `/*__SKILL_MAP_DATA__*/` and
  `/*__SKILL_MAP_META__*/null` markers.
- **Releases:** versions change only through `bump_version.py`; `.github/workflows/*` is untouched.

## Acceptance tests

- `python3 scripts/build_skill_map.py`, `python3 scripts/validate_skill_map.py` and `--check-stale`
  pass.
- `python3 scripts/render_skill_map_docs.py` is idempotent.
- `python3 scripts/validate_plugin_configs.py` and `python3 scripts/bump_version.py --check` pass.
- The full pytest suite plus `tests/skill-map/*.js` pass, apart from the known root-sandbox failure
  `test_stale_temp_dirs_are_swept_and_unwritable_cache_is_explained`.
- Vocabulary counts are topics ≤25 and stacks ≤10, with no unused non-condition slug.
- The static map has a `fork-of` edge from `skill:project-launcher/rhize-visual-plan`.
- The viewer renders without console errors at 1440px and 390px. Sliders change the layout; tooltips
  still work.

## Implementation order

1. **Parallel lanes in isolated worktrees:**
   - Lane A: tag consolidation.
   - Lane B: provenance, remediators and the edge re-verification.
   - Coordinator: viewer forces and the outreach fix.
2. **Merge:** integrate both lanes, regenerate the map and docs, run validators.
3. **Bump:** version bumps and CHANGELOG entries for the changed plugins.
4. **Verify:** full verification and a browser check of the viewer; republish the artifact.
5. **Ship:** fast-forward `main` and push, then delete the feature branch.
