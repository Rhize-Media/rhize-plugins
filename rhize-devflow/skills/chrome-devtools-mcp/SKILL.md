---
name: chrome-devtools-mcp
tier: custom
domain: dev-flow
maturity: stable
version: 2.0.0
description: >-
  DevTools-protocol mechanics reference for the `chrome-devtools` MCP server, used by
  `/rhize-devflow:browser-qa` when that server is the active browser capability. Use when the
  user asks specifically about Chrome DevTools MCP tool names/parameters, connecting to a
  running Chrome instance, or MCP-level configuration/troubleshooting for that server — not
  for general "test in the browser" requests, which should go through
  `/rhize-devflow:browser-qa` instead.
metadata:
  rhize:
    topics: [automation, observability]
    stacks: [testing, nextjs]
    dependsOn: ["mcp:chrome-devtools"]

---

# Chrome DevTools MCP Server Skill

> DevTools-protocol mechanics for the `chrome-devtools` MCP server — the tool this plugin's
> canonical browser command calls when that server is the active browser capability.

**Run a Rhize acceptance check?** Use `/rhize-devflow:browser-qa` — it owns the scenario
sequencing (functional path, console/network errors, accessibility smoke, responsive layout,
performance) and defers to this skill only for DevTools-protocol tool mechanics once
`chrome-devtools` is the detected capability. This skill does not itself define an
acceptance workflow, to avoid a second, drifting copy of that sequence.

For anything beyond the mechanics below — full API reference, config flags, CI setup
patterns — see the official [chrome-devtools-mcp repository](https://github.com/ChromeDevTools/chrome-devtools-mcp)
and [npm package](https://npmjs.org/package/chrome-devtools-mcp); this skill does not
duplicate that documentation.

---

## Core Capabilities

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   CHROME DEVTOOLS MCP SERVER                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐          ┌──────────────────────────────┐ │
│  │   MCP CLIENT     │          │     CHROME INSTANCE          │ │
│  │ (Claude/Cursor)  │          │   (Stable/Canary/Beta)       │ │
│  ├──────────────────┤          ├──────────────────────────────┤ │
│  │ • Send prompts   │  ──────► │ • DevTools Protocol          │ │
│  │ • Receive results│  Tools   │ • Performance traces         │ │
│  │ • View screenshots│         │ • Network inspection         │ │
│  │ • Analyze data   │  ◄────── │ • Console access             │ │
│  │                  │  Results │ • DOM snapshots              │ │
│  └──────────────────┘          └──────────────────────────────┘ │
│         │                                   │                    │
│         ▼                                   ▼                    │
│  ┌──────────────────┐          ┌──────────────────────────────┐ │
│  │   Puppeteer      │          │   Chrome DevTools            │ │
│  │   Automation     │          │   Protocol (CDP)             │ │
│  │   Layer          │          │   Direct Access              │ │
│  └──────────────────┘          └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Tool Categories

| Category | Tools | Primary Use Case |
|----------|-------|------------------|
| **Input Automation** | `click`, `fill`, `fill_form`, `drag`, `hover`, `press_key`, `upload_file`, `handle_dialog` | Form testing, UI interactions |
| **Navigation** | `navigate_page`, `new_page`, `close_page`, `list_pages`, `select_page`, `wait_for` | Multi-tab control, routing tests |
| **Performance** | `performance_start_trace`, `performance_stop_trace`, `performance_analyze_insight` | Core Web Vitals, profiling |
| **Network** | `list_network_requests`, `get_network_request` | API debugging, CORS issues |
| **Debugging** | `list_console_messages`, `get_console_message`, `evaluate_script`, `take_screenshot`, `take_snapshot` | Error investigation, visual testing |
| **Emulation** | `emulate`, `resize_page` | Device testing, responsive design |

---

## Installation

```bash
claude mcp add --scope user chrome-devtools npx chrome-devtools-mcp@latest
```

For manual MCP config, headless/CI flags, custom viewports, or connecting to an existing
Chrome instance's debug port, see the official
[chrome-devtools-mcp README](https://github.com/ChromeDevTools/chrome-devtools-mcp#readme) —
this skill does not restate its configuration surface.

---

## Tool mechanics

Use the active tool schema for exact names and parameters. Read a fresh page snapshot before
interacting and use the element/page references supplied by that server. Do not translate
selectors or old parameter tables into guessed calls. Consult the
[official tool reference](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/tool-reference.md)
when needed; installed schemas govern version-specific behavior. Detect screenshot, accessibility,
network, console and performance capabilities individually and report unsupported checks.

---

## Common Workflows

Rhize's scenario sequencing (functional path → console/network → accessibility smoke →
responsive layout → performance-on-request) lives in `/rhize-devflow:browser-qa`, not here
— run that command for an acceptance check. [EXAMPLES.md](references/EXAMPLES.md) has
detailed per-tool prompt patterns for cases outside that sequencing.

---

## Integration with Other MCP Servers

| Workflow | MCP Combination | Use Case |
|----------|-----------------|----------|
| **Bug Investigation** | Sentry → Chrome DevTools | Get error context, reproduce in browser |
| **Deployment Verification** | Vercel → Chrome DevTools | Deploy, then visual/performance test |
| **Full-Stack Debug** | Supabase → Chrome DevTools | Check DB state, verify frontend |

---

## Connecting to Running Chrome

For maintaining browser state or working around sandbox restrictions, connect via
`--browser-url` to a Chrome instance started with `--remote-debugging-port`. See
[TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) for the full setup and the debug-port
security caveat (it exposes the browser to any local application — don't browse sensitive
sites with it open).

---

## Requirements

- **Node.js**: v20.19+ (latest maintenance LTS)
- **Chrome**: Current stable version or newer
- **npm**: Latest version

---

## Bundled References

- [EXAMPLES.md](references/EXAMPLES.md) - 📖 READ: Detailed prompts and integration patterns
- [TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) - 📖 READ: Platform-specific solutions

---

## Resources

- [Official Repository](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [npm Package](https://npmjs.org/package/chrome-devtools-mcp)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
