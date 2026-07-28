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
- [ ] Replace the ingested `strategic-compact` skill's ECC hook (`suggest-compact.js`) with a Rhize-owned equivalent. The upstream hook sizes the context window by sniffing the model id for a `[1m]` marker; Opus 5 carries a 1M window with no marker, so the hook divides ~195k by 200k and reports **97% when the true figure is 20%** — a false compact warning on every turn below 200k. It self-corrects only above 200k (its `tokens > 200_000 → assume 1M` fallback), so the error is invisible from the message alone. `context_analyzer.py`'s `resolve_context_limit()` already implements the correct precedence and is the reference. Interim mitigation: set `ECC_CONTEXT_WINDOW_TOKENS` in `~/.claude/settings.json` — the upstream hook honors it first.
- [ ] Decide the home for the replacement: a plugin hook, or a `@rhize/skill-forge` subcommand invoked from a thin hook (per the marketplace's move-capability-to-the-npm-CLI direction). A PreToolUse hook shelling out to `npx` on every tool call has a real latency cost worth measuring first.

### seo-aeo-geo
- [ ] (none yet)

### New Plugin Ideas
- (add ideas here as they come up)
