# Security Policy

Rhize Plugins is a marketplace of Claude Code / Cowork plugins. Several plugins ship
`hooks/hooks.json` entries and `setup/manifest.json` opt-in items that execute **shell
commands on the machine of anyone who installs and wires them up**. That is the specific
threat model this policy addresses — please read "What installing a plugin means" below
before reporting, so you know what's in scope.

## Reporting a vulnerability

**Preferred: GitHub private security advisories.**
Open one at https://github.com/Rhize-Media/rhize-plugins/security/advisories/new — this
notifies the maintainer privately without exposing the issue (or a working exploit) in a
public issue before a fix ships. Private vulnerability reporting is enabled on this
repository.

If you can't use GitHub's advisory flow for some reason, email **jim@rhize.media** with
"SECURITY" in the subject line.

Please do not open a public GitHub issue for a security vulnerability.

### What to include

- Which plugin/skill/hook/command is affected (path, e.g. `seo-aeo-geo/hooks/hooks.json`)
- What the hook or script does that's unsafe (arbitrary command execution, path traversal,
  secret exposure, unsafe `eval`, etc.) and, if possible, a minimal repro
- Impact you'd expect for an installer who enables it

## Response time

This is a solo-maintainer project. You should get an **acknowledgment within 7 days**.
There's no formal SLA for a fix beyond that — timeline depends on severity and complexity —
but you'll be kept informed via the advisory thread.

## Supported versions

This repo ships plugins, not a single versioned application. Only the current `main` branch
is supported; fixes land as a new patch/minor version of the affected plugin (see
`CHANGELOG.md` and each plugin's `.claude-plugin/plugin.json`). There is no backport policy
for older plugin versions.

## What installing a plugin means (read this before reporting or before installing)

Adding this marketplace and enabling a plugin does **not** by itself run anything — hooks are
opt-in. But once a hook is wired into a project's `.claude/settings.json` (by hand, or via the
`rhize-ops:rhize-setup` wizard — see `rhize-ops/commands/rhize-setup.md`), it executes local
shell commands automatically on matching events (`PreToolUse`, `UserPromptSubmit`, etc.),
with your OS user's permissions.

Before enabling any plugin's hooks, review:

1. **`<plugin>/hooks/hooks.json`** — the hook registrations Claude Code will wire up: which
   event/matcher triggers each one, and the exact command line it runs.
2. **The scripts those commands invoke** (usually under `<plugin>/hooks/*.sh` or `*.js`) —
   read what the script actually does, not just its filename.
3. **`<plugin>/setup/manifest.json`** — the plugin's declared catalog of *available* opt-in
   hook items (tier `T3` advisory / `T4` blocking) and any external dependencies (MCP
   servers, credentials) each one assumes. A manifest entry existing does not mean it's
   active — check the project's `.claude/settings.json` for what's actually wired, and any
   `env.ECC_DISABLED_HOOKS` / `env.ECC_GATEGUARD` overrides that might silently neuter a hook
   you thought was live.
4. **MCP server configuration** (`<plugin>/.mcp.json`, if present) — what external service
   each server talks to, and what credentials it expects.

If a hook or script does something you didn't expect from its description, treat that as a
security bug and report it here rather than silently disabling it and moving on — the next
installer won't know to check.

## Known non-issues

- Plugins running arbitrary shell commands **by design**, when a hook is explicitly wired by
  the installer and does what its manifest description says, is not itself a vulnerability —
  that's how Claude Code hooks work. Report a mismatch between description and behavior, or a
  hook that runs without being wired.
- This repo intentionally ships capability as installable plugins rather than a monolithic
  `.claude/settings.json` or `.claude/skills|agents|commands` — see `CLAUDE.md`'s curation
  rule. That structure itself is not a finding.
