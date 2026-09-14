# Description pilot impact map

## Current behavior

Three skill descriptions contain broad trigger language that can select context engineering on
generic start/done/commit wording and can blur new-project launch, standalone visual-plan, and
ordinary code-change requests. The current skill bodies and metadata define the workflows to
preserve.

## Intended semantic delta

Change only the description frontmatter in:

- `rhize-context-manager/skills/context-engineering/SKILL.md`
- `project-launcher/skills/project-launcher/SKILL.md`
- `project-launcher/skills/rhize-visual-plan/SKILL.md`

Update routing explanations in `rhize-context-manager/README.md`,
`rhize-context-manager/GUIDE.md`, `project-launcher/README.md`, and
`project-launcher/GUIDE.md`. Add the static pilot fixture at
`evals/skill-description-pilot/fixture.json`, this documentation, and its focused invariant
test at `tests/evals/test_skill_description_pilot.py`.

## Invariants

Preserve skill names, metadata, bodies, relative references, invocation policy, GSD v2 handoff,
local `rhize-plan` viewer and HTML export, Obsidian fallback and vault save behavior, and all
existing task workflows. Fixture expectations describe initial skill selection; downstream
workflow calls remain allowed. Static fixture checks do not establish runtime behavior or savings.

## Acceptance tests

Run `python3 -m pytest tests/evals/test_skill_description_pilot.py -q` and the existing
`tests/config-lint/test_claude_md_router.py` plus
`tests/config-lint/test_description_parity.py`. Check that only the three description fields
changed in the skill sources and that the fixture source/body/metadata hashes agree.

## Implementation order

Record source descriptions and baseline hashes, define routing cases, change only the three
description fields, update the four plugin README/GUIDE notes, run focused checks, inspect the
diff, and reconcile the exact file list. The coordinator owns generated documents, changelogs,
versions, host runs, integration, and release checks.

## Coordinator integration and adoption boundary

The candidate retains implicit session closure, existing-PRD gap review, and risky single-file
sign-off. Its fixture now includes these as positive first-selection cases. Skill bodies and
other skill metadata remain byte-identical to the pinned baseline.

Prepare package metadata with `scripts/bump_version.py` for `rhize-context-manager` and
`project-launcher`, then regenerate `generated/skill-map.static.json`,
`generated/skill-map.indexes.json`, `generated/SKILL-CATALOG.md`, managed README tables and
`docs/README.md`. The helper owns `.claude-plugin/marketplace.json`, both plugins' Claude and
Codex plugin manifests, and root/plugin `CHANGELOG.md` entries. These are source preparation;
no install, push, merge or adoption is implied. Adoption requires matched host evidence.
