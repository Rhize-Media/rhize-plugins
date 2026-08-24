# Supplying secrets to MCP servers

How Rhize plugins deliver an API credential to an MCP server without ever writing
that credential into a file, and why the obvious approach (`"${VAR}"` in the
`env` block) is not reliable enough to depend on.

---

## The failure this prevents

An MCP config can ask for a credential like this:

```json
"env": { "OBSIDIAN_API_KEY": "${OBSIDIAN_API_KEY}" }
```

Claude Code substitutes `${VAR}` from **its own process environment** at the
moment the config loads. Two outcomes, and only one of them is the one you want:

| Variable in Claude Code's environment | What the server receives |
| ------------------------------------- | ------------------------ |
| present                               | the real value — works   |
| **absent**                            | the **literal string** `${OBSIDIAN_API_KEY}` |

In the second case the server authenticates with the literal seven-to-thirty
characters `${OBSIDIAN_API_KEY}` and returns a 401 or 403. Nothing in that error
mentions configuration, so it reads as a broken token, an expired key, or a
server-side outage. Meanwhile a perfectly valid credential may be sitting in the
login keychain, unused.

Claude Code does emit a load-time warning for this
(`Missing environment variables: <NAME>`), but it appears in `claude mcp list`
output rather than at the point of failure, so in practice it is missed.

**The part that makes this genuinely dangerous:** whether the variable is present
depends on *how Claude Code was launched*. A shell-launched session and a
GUI-launched session do not necessarily carry the same environment. The same
committed config therefore works on Monday and fails on Tuesday, with no file
having changed. That is why `${VAR}` is documented here as unsuitable for
secrets — not because it is broken, but because it is **conditional**.

> Verified empirically against Claude Code 2.1.233 on 2026-08-19 with a probe MCP
> server that reported its own environment: a set variable expanded correctly, an
> unset one arrived as the literal `${...}` string.

---

## The mechanism

Rhize plugins invoke a committed POSIX-sh shim instead of the server directly:

```json
{
  "mcpServers": {
    "obsidian-mcp-server": {
      "command": "${CLAUDE_PLUGIN_ROOT}/scripts/mcp-secret-launcher.sh",
      "args": ["OBSIDIAN_API_KEY", "--", "npx", "obsidian-mcp-server"],
      "env": {
        "OBSIDIAN_BASE_URL": "https://127.0.0.1:27124"
      }
    }
  }
}
```

Everything before `--` is a **variable name** to resolve. Everything after `--`
is the command to run once they are resolved. Non-secret settings stay in `env`
as plain literals.

`${CLAUDE_PLUGIN_ROOT}` is Claude Code's own plugin-directory variable, so the
reference stays correct wherever the plugin is installed.

### Resolution order

1. **`mcp-secret-launcher`** — looked up on `PATH`, then at
   `~/.local/bin/mcp-secret-launcher`. It reads each variable from the macOS
   login keychain at service `claude-code:<VAR>` and exports it into that one
   child process only. Secrets never enter an interactive shell, so an accidental
   `env` dump cannot see them.
2. **Plain environment inheritance** — no launcher installed, but the variables
   are already exported? Run the server with what is there. This is the path that
   lets the plugin work on Linux, inside Claude Cowork, and on a teammate's
   machine with no Rhize tooling.
3. **Refuse to start** — neither available. Exit `78` (`EX_CONFIG`) with a
   message naming the missing variables and giving both remedies.

Step 3 is deliberate. Starting a server that provably cannot authenticate just
converts a setup error into an opaque runtime 401 — the exact confusion this
whole mechanism exists to eliminate.

---

## Setup

### macOS (recommended)

Store each credential in the login keychain:

```bash
security add-generic-password -a "$USER" -s "claude-code:OBSIDIAN_API_KEY" -l "OBSIDIAN_API_KEY" -w '<value>' -U
```

Confirm an item exists **without printing its value**:

```bash
security find-generic-password -a "$USER" -s "claude-code:OBSIDIAN_API_KEY" >/dev/null 2>&1 && echo present
```

> Never use `-w` on `find-generic-password` in a session whose output is being
> recorded — that flag prints the secret in plaintext.

Then install `mcp-secret-launcher` at `~/.local/bin/mcp-secret-launcher`
(`chmod 755`). It takes the same `VAR ... -- command ...` argument form as the
shim and is what the shim delegates to.

### Linux, Claude Cowork, or any machine without the launcher

Export the variables in the environment Claude Code is started from:

```bash
export OBSIDIAN_API_KEY=...
```

The shim detects them and runs the server normally. No keychain, no launcher.

---

## Variables by plugin

| Plugin | Variables |
| ------ | --------- |
| `obsidian-second-brain` | `OBSIDIAN_API_KEY` |
| `seo-aeo-geo` | `DATAFORSEO_USERNAME`, `DATAFORSEO_PASSWORD` |

---

## Known gap: HTTP-transport servers

A server configured with a `headers` block has **no child process to wrap**, so
the shim cannot cover it:

```json
"seo-utils": {
  "url": "http://localhost:19515/mcp",
  "headers": { "Authorization": "Bearer ${SEO_UTILS_TOKEN}" }
}
```

These remain subject to the conditional-expansion behaviour described above. The
only way to make one reliable today is to guarantee the variable is present in
the environment Claude Code itself is launched from — which reintroduces ambient
exposure for that variable, and is a trade-off to make deliberately rather than
by default. Track them; do not paper over them with a workaround.

---

## Rules

- **Never** put a credential value in `.mcp.json`, a plugin file, or any file
  under version control.
- **Never** use `${VAR}` in an `env` block for a secret. Use the shim.
- Non-secret configuration (base URLs, feature flags, module lists) belongs in
  `env` as a plain literal — the shim is only for credentials.
- Every change to an MCP config requires a **session restart** to take effect.

## Detecting regressions

This finds every `${...}` still present in an MCP config across all
config locations:

```bash
python3 - <<'PY'
import json, os, re, glob
pat = re.compile(r"\$\{[^}]+\}")
files  = glob.glob(os.path.expanduser("~/.claude/plugins/**/.mcp.json"), recursive=True)
files += glob.glob(os.path.expanduser("~/dev-local/**/.mcp.json"), recursive=True)
files += [os.path.expanduser("~/.claude.json")]
for p in files:
    if "/node_modules/" in p or "/test/fixtures/" in p:
        continue
    try:
        d = json.load(open(p))
    except Exception:
        continue
    for name, cfg in (d.get("mcpServers") or {}).items():
        if not isinstance(cfg, dict):
            continue
        for block in ("env", "headers"):
            for k, v in (cfg.get(block) or {}).items():
                if isinstance(v, str) and pat.search(v):
                    kind = "HTTP" if ("url" in cfg or "headers" in cfg) else "stdio"
                    print(f"{kind:5}  {name:22} {block}.{k:24} {p}")
PY
```

`stdio` rows are actionable — migrate them to the shim. `HTTP` rows are the
known gap above.
