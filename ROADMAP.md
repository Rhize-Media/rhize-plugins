# Roadmap

Tracked enhancements and future ideas for the Rhize Plugins marketplace.

## Backlog

### Marketplace Infrastructure
- [ ] Use git submodule for `obsidian-second-brain/` to auto-sync with [kepano/obsidian-second-brain](https://github.com/kepano/obsidian-second-brain) upstream
- [x] Add version bump script to coordinate plugin.json + marketplace.json + changelog updates — `scripts/bump_version.py` (+ `/rhize-ops:bump-version`, `.githooks/pre-push`, CI version-check + tag-release)

### obsidian-second-brain

- [x] Trigger accuracy evals (32 cases across 8 skills)
- [x] Quality evals (8 cases, one per skill — reference knowledge only)
- [ ] Command evals — requires Obsidian MCP Server + running Obsidian instance. Covers `/vault-search`, `/vault-setup`, `/vault-align`, and other CLI commands against a test vault.
- [ ] Sync with upstream kepano/obsidian-second-brain when new features land
- [ ] Eval suite for vault-setup wizard — test fresh vault and existing vault paths
- [ ] Eval suite for vault-align — test health check scoring and fix execution
- [ ] Explore `obsidian eval` for deeper plugin configuration inspection during setup
- [ ] Investigate Obsidian URI scheme for plugin install links (obsidian://show-plugin?id=dataview)

### rhize-context-manager
- [x] Replace ECC's `suggest-compact` hook with a Rhize-owned equivalent — `hooks/context-window-monitor.js`. Upstream sized the window by sniffing the model id for a `[1m]` marker; Opus 5 has 1M and no marker, so it reported **97% where the truth was 20%**, wrong for every turn below 200k and self-correcting only above it. Replacement resolves env → marker → verified known-model table → observed evidence → 200k. 9-case self-test, verified end-to-end against a live transcript.
- [x] Decide the replacement's home — **plugin hook**, not a `@rhize/skill-forge` subcommand. The npm-CLI direction is right for user-invoked capability, but a `PreToolUse` hook pays an `npx` spawn on every matching tool call; a vendored node script has no such cost and versions with the marketplace.
- [ ] Extend `KNOWN_WINDOWS` beyond `claude-opus-5` as other model windows are confirmed. Deliberately sparse — an unverified entry outranks the observed-usage evidence beneath it, so a wrong entry is worse than a missing one.
- [ ] Consider widening the hook matcher past `Edit|Write`. Read/Bash results are the largest context consumers, but every added matcher is another node spawn; measure before broadening.

### seo-aeo-geo
- [ ] (none yet)

### New Plugin Ideas
- (add ideas here as they come up)
