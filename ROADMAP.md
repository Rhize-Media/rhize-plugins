# Roadmap

Tracked enhancements and future ideas for the Rhize Plugins marketplace.

## Backlog

### Marketplace Infrastructure
- [ ] Use git submodule for `obsidian-skills-plugin/` to auto-sync with [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) upstream
- [ ] Add version bump script to coordinate plugin.json + marketplace.json + changelog updates

### obsidian-skills

- [x] Trigger accuracy evals (32 cases across 8 skills)
- [x] Quality evals (8 cases, one per skill — reference knowledge only)
- [ ] Command evals — requires Obsidian MCP Server + running Obsidian instance. Covers `/vault-search`, `/vault-setup`, `/vault-align`, and other CLI commands against a test vault.
- [ ] Sync with upstream kepano/obsidian-skills when new features land
- [ ] Eval suite for vault-setup wizard — test fresh vault and existing vault paths
- [ ] Eval suite for vault-align — test health check scoring and fix execution
- [ ] Explore `obsidian eval` for deeper plugin configuration inspection during setup
- [ ] Investigate Obsidian URI scheme for plugin install links (obsidian://show-plugin?id=dataview)

### seo-aeo-geo
- [ ] (none yet)

### New Plugin Ideas
- (add ideas here as they come up)
