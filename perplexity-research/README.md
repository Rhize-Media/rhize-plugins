# Perplexity Research

Use your Perplexity subscription for Search and Research from Claude Code or Codex on macOS.
Eleven MCP tools provide durable jobs, follow-ups, explicit citation mappings, GET-only
recovery, Markdown export, local cancellation and encrypted browser-to-Keychain session setup.
This is an experimental integration with undocumented web endpoints, not Perplexity's API.

## Installation and setup

Install `perplexity-research@rhize-plugins` from the Rhize marketplace. For Codex:

```sh
codex plugin marketplace add https://github.com/Rhize-Media/rhize-plugins
codex plugin add perplexity-research@rhize-plugins
```

For an existing marketplace use `codex plugin marketplace upgrade rhize-plugins` first.
In Claude Code, use `/plugin install perplexity-research@rhize-plugins`.
macOS Keychain, Python 3.10+ and `cryptography` are required. Native session transfer also
needs a Node-capable browser host with authorized, scoped CDP access to the signed-in tab.
No browser access is needed for querying once the session has been stored.

Create a private Python environment, or select an existing interpreter that meets the requirements:

```sh
umask 077
mkdir -p "$HOME/.config/perplexity-research"
chmod 700 "$HOME/.config/perplexity-research"
python3 -m venv "$HOME/.config/perplexity-research/venv"
"$HOME/.config/perplexity-research/venv/bin/python3" -m pip install 'cryptography==46.0.6'
```

Create `~/.config/perplexity-research/config.json` as a mode-600, owned regular file:

```json
{
  "pythonExecutable": "~/.config/perplexity-research/venv/bin/python3",
  "stateDir": "~/.local/share/perplexity-research",
  "authorizationReference": "~/.config/perplexity-research/authorization.txt",
  "keychainService": "perplexity-research-cookies"
}
```

The [JSON Schema](config/schema.json) documents these supported settings; omitted fields inherit [config/defaults.json](config/defaults.json).
`pythonExecutable` must be selected before MCP startup. Paths must be absolute or start with `~/`.
The Keychain service must start with a letter/digit and contain only letters, digits, `.`, `_`,
`:`, or `-` (128 characters maximum). JSON never contains cookies, passwords or authorization text.
Unknown fields, malformed or oversized JSON, shared files, symlinks and hardlinks are refused.
The launcher uses `python3` on PATH for standard-library configuration loading, then executes
only the selected Python 3.10+ runtime with `cryptography`. It does not install dependencies or
fall back to a different runtime. CLI and MCP read the same JSON; CLI flags can override state,
service and submission authorization for a single invocation. Detached workers retain the selected service.
The plugin cache contains no machine-specific paths, credentials, authorization text or jobs.

Before submitting, create the configured `authorizationReference` as an owned,
unshared mode-600 regular file documenting the user's actual authorization and access basis.
Do not invent provider permission or put passwords/cookies in it. Only its hash enters job state.
Health, models and existing results work without a submission authorization file.

Restart the host after installation or manifest/adapter updates. Ask to connect your Perplexity
session: the plugin provides an encrypted local handoff to the configured `keychainService` in Keychain.
Cookies must never pass through chat, MCP arguments, source or logs. A sign-in challenge requires
the ordinary browser UI. Then call `research_health`; authentication tests never submit queries.

## Using and maintaining the plugin

See [GUIDE.md](GUIDE.md) for everyday workflows and [the complete technical guide](docs/perplexity-local-bridge.md)
for the eleven tools, validation rules, limits and recorded live evidence. The [feasibility review](docs/perplexity-pro-feasibility.md)
records the upstream review and access limitations; its [MIT notice](docs/perplexity-upstream-LICENSE.txt) ships here.

Run offline checks from the repository root: `python3 -m pytest -q tests/perplexity-research`.
The runtime is self-contained in `scripts/`; it does not import sibling plugins or repository helpers.
No hooks, background polling schedule, API-key fallback or automatic retries are installed.

## Migration, updates and removal

Keep only one Perplexity plugin active. When migrating from `perplexity-research@perplexity-local`,
finish/cancel active local workers, install the marketplace version, verify its source and MCP startup,
then remove the local-only plugin with `codex plugin remove perplexity-research@perplexity-local`.
Restart the host to remove the old tool registration. Do not create a duplicate standalone MCP entry.
Before switching, set `stateDir`, `authorizationReference` and `keychainService` in your private JSON to the existing locations and service name. This preserves jobs, request IDs and session without moving or deleting them. There is no automatic discovery or migration of legacy organization-specific paths. Verify existing reports before removing the old registration.

For updates, upgrade the marketplace and run `codex plugin add perplexity-research@rhize-plugins`
again. Verify the installed version and health; retain prior source for rollback. Uninstalling
with `codex plugin remove perplexity-research@rhize-plugins` leaves private state and Keychain intact.
Deleting that state separately would remove duplicate protection and saved reports.

## Skill inventory

<!-- SKILL-MAP:BEGIN -->
| Skill | Description | Topics |
| --- | --- | --- |
| `perplexity-research` | Use Perplexity subscription Search or Research for user-requested cited answers and reports. | automation, evidence, search |
<!-- SKILL-MAP:END -->
