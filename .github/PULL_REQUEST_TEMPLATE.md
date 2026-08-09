## What does this change?

<!-- Plugin(s)/skill(s)/hook(s) touched, and why. -->

## Curation check (required if this adds or ingests a skill)

Per `CLAUDE.md`'s **Curation Rule — close gaps, never duplicate**: a Rhize skill exists to
close a gap a proven plugin leaves open, and must never re-ship a skill an enabled upstream
plugin already provides.

- [ ] Not applicable — this PR doesn't add or ingest a skill
- [ ] I checked whether an enabled plugin already ships this skill/capability, by name and by
      capability, and it does not
- [ ] If this is a fork of an upstream skill, I recorded *why the fork is load-bearing* in
      `SOURCES.md` and defined a real Drift check

## Documentation (required if this adds/removes/changes a skill, command, hook, MCP connector, or plugin)

Per `CLAUDE.md`'s **Documentation Maintenance** rule — undocumented capability is treated the
same as untested capability:

- [ ] Not applicable — no skill/command/hook/MCP connector/plugin was added, removed, or
      materially changed
- [ ] Updated the plugin's own `README.md` (skill/command tables, architecture tree, setup
      steps) to match reality
- [ ] Updated the plugin's `GUIDE.md` (created one if it didn't exist) so the new/changed
      capability is discoverable in plain language, with an example prompt
- [ ] If a whole plugin was added/removed: updated the root `README.md` Plugin Catalog table
      and `.claude-plugin/marketplace.json`, keeping `version` in sync with the plugin's own
      `plugin.json`
- [ ] Added a `CHANGELOG.md` entry (user-visible changes only)

## Version bump

- [ ] Not applicable — no plugin version change needed
- [ ] Version was bumped via `python3 scripts/bump_version.py --plugin <name> --level
      minor|patch|major` (never hand-edited in `plugin.json`/`marketplace.json`)

## Testing

<!-- How did you verify this? Eval suite run, manual skill invocation, etc. -->
