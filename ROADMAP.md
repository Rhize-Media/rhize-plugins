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
- [x] Ship native v2 source-bound context packs and bounded multi-source memory previews for Claude Code and Codex.
- [x] Ship an offline governed Graphify/Neo4j ontology, staged fake adapter, read-only memory adapter, reversible identity review, and decision-accountability extension.
- [ ] RT-158: measure unified-memory preview benefit before any bounded injection canary; keep write-back disabled.
- [ ] RT-159: run the isolated live Neo4j canary, backup/restore rehearsal, and driver/constraint verification before publication.
- [ ] RT-160: calibrate identity review by entity type before considering any automatic `SAME_AS`; protected identities remain deterministic.
- [ ] RT-161: validate durable decision recording/query/correction before enabling anything beyond offline preview.
- [ ] RT-164: implement and validate an ACL-aware qmd adapter before compiled pages can enter qmd collections.

### Cross-plugin agent workflow

- [x] Ship dual-host ephemeral task-graph validation and terminal receipt-v2 lifecycle in `rhize-ops`.
- [x] Ship dual-host test-contract classification and fail-closed, state-bound packet validation in `rhize-devflow`.
- [x] Ship evidence-bound compiled knowledge in `obsidian-second-brain` with source authority retained outside derived pages/graphs.
- [ ] RT-155 and RT-156: collect host-stratified task-graph and test-evidence calibration before automatic promotion decisions.
- [ ] RT-163: implement a trusted sandbox adapter before behavioral evidence can execute repository package scripts.
- [ ] RT-157: measure compiled-knowledge maintenance and invalidation before scheduling rebuilds.
- [x] RT-166: expose RT-138's compile-only Functionize surface as a separately routed skill-map node without crossing registry, trust, promotion, or execution gates.
- [ ] RT-140/RT-145: prove material value with a real reviewed Functionize proposal before any registry promotion or broader plugin packaging claim.

### seo-aeo-geo
- [ ] (none yet)

### New Plugin Ideas
- (add ideas here as they come up)
