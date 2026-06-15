---
name: chrome-devtools-mcp
tier: custom
domain: dev-flow
maturity: stable
version: 1.0.0
description: >-
  Browser automation, debugging, and performance analysis via the official Google Chrome DevTools
  MCP server (Puppeteer-backed, wait-aware). Use when the user wants to "test in browser", "check
  performance", "debug network", "take a screenshot", "fill a form", inspect "console errors",
  "inspect the page", "automate the browser", diagnose "CORS issues", or run a "lighthouse audit" —
  including Core Web Vitals traces, network waterfalls, and visual checks on Next.js/Sanity/Payload
  preview URLs. Pairs with gsd-browser-harness; prefer this for DevTools-protocol performance and
  network introspection.
---

# Chrome DevTools MCP Server Skill

> Browser automation, debugging, and performance analysis via Chrome DevTools Protocol

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

### Claude Code (Recommended)

```bash
# User-scope (available across all projects)
claude mcp add --scope user chrome-devtools npx chrome-devtools-mcp@latest

# Project-scope (specific project only)
claude mcp add chrome-devtools npx chrome-devtools-mcp@latest
```

### Manual Configuration

Add to your MCP configuration file:

**Location:**
- Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Claude Code: `~/.claude/settings.json` or project `.mcp.json`

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

### Verify Installation

Test with this prompt:
```
Check the performance of https://example.com
```

The MCP server should launch Chrome and return a performance report.

---

## Configuration Options

### Basic Options

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--headless` | boolean | `false` | Run without visible browser window |
| `--isolated` | boolean | `false` | Use temporary profile (cleared after close) |
| `--channel` | string | `stable` | Chrome channel: `stable`, `canary`, `beta`, `dev` |
| `--viewport` | string | - | Initial viewport size, e.g., `1440x900` |

### Connection Options

| Flag | Type | Description |
|------|------|-------------|
| `--browserUrl`, `-u` | string | Connect to running Chrome via port forwarding |
| `--wsEndpoint`, `-w` | string | WebSocket endpoint for direct connection |
| `--executablePath`, `-e` | string | Path to custom Chrome executable |

### Configuration Examples

**Development Setup (Persistent State):**
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--viewport=1440x900"]
    }
  }
}
```

**CI/CD Setup (Headless):**
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--headless=true", "--isolated=true"]
    }
  }
}
```

**Connect to Existing Chrome:**
```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url=http://127.0.0.1:9222"]
    }
  }
}
```

---

## Tool Reference

### Input Automation

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `click` | Click element | `selector`, `button`, `clickCount` |
| `fill` | Fill input field | `selector`, `value` |
| `fill_form` | Fill multiple fields | `fields[]`, `submit` |
| `hover` | Hover over element | `selector` |
| `press_key` | Send keyboard event | `key`, `modifiers[]` |
| `drag` | Drag between elements | `sourceSelector`, `targetSelector` |
| `upload_file` | Upload to file input | `selector`, `filePath` |
| `handle_dialog` | Handle JS dialogs | `action`, `promptText` |

### Navigation

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `navigate_page` | Go to URL | `url`, `waitUntil` |
| `new_page` | Open new tab | `url` |
| `close_page` | Close tab | `pageId` |
| `list_pages` | List open tabs | - |
| `select_page` | Switch tab | `pageId` |
| `wait_for` | Wait for condition | `selector`, `timeout`, `state` |

### Performance

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `performance_start_trace` | Begin recording | `categories` |
| `performance_stop_trace` | Stop and get data | - |
| `performance_analyze_insight` | Analyze specific insight | `insightType` |

### Network

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `list_network_requests` | Get all requests | `filter` |
| `get_network_request` | Get request details | `requestId` |

### Debugging

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `list_console_messages` | Get console output | `level` |
| `get_console_message` | Get message details | `messageId` |
| `evaluate_script` | Run JS in page | `expression` |
| `take_screenshot` | Capture image | `fullPage`, `selector`, `format` |
| `take_snapshot` | Accessibility tree | `saveToDisk` |

### Emulation

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `emulate` | Emulate device | `device` or `{width, height, ...}` |
| `resize_page` | Change viewport | `width`, `height` |

---

## Common Workflows

### Performance Analysis
```markdown
1. Navigate to target URL
2. Start performance trace
3. Perform user interactions (scroll, click)
4. Stop trace and analyze insights
5. Get actionable recommendations

Prompt: "Check the performance of http://localhost:3000/dashboard, 
scroll through the page, and identify render-blocking resources"
```

### Network Debugging
```markdown
1. Navigate to page
2. Reproduce the issue (form submit, API call)
3. List network requests (filter for failures)
4. Get full request details (headers, body)
5. Identify issues (CORS, auth, payload)

Prompt: "Navigate to http://localhost:3000/login, submit with 
test@example.com / password123, and show any failed API requests"
```

### Visual Testing
```markdown
1. Navigate to URL
2. Optionally emulate device
3. Take screenshot (full page or element)
4. Compare across viewports

Prompt: "Take screenshots of http://localhost:3000/pricing at 
desktop (1440x900), tablet (768x1024), and mobile (375x667)"
```

### Form Automation
```markdown
1. Navigate to form page
2. Fill form fields
3. Handle dialogs
4. Submit and verify result

Prompt: "Fill the registration form at http://localhost:3000/register:
name=Test User, email=test@example.com, password=Secure123!
Then submit and verify no console errors"
```

---

## Integration with Other MCP Servers

| Workflow | MCP Combination | Use Case |
|----------|-----------------|----------|
| **Bug Investigation** | Sentry → Chrome DevTools | Get error context, reproduce in browser |
| **Deployment Verification** | Vercel → Chrome DevTools | Deploy, then visual/performance test |
| **Full-Stack Debug** | Supabase → Chrome DevTools | Check DB state, verify frontend |

---

## Connecting to Running Chrome

For maintaining browser state or working around sandbox restrictions:

### 1. Start Chrome with Debug Port
```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-mcp-profile
```

### 2. Configure MCP Connection
```json
{
  "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url=http://127.0.0.1:9222"]
}
```

> ⚠️ **Security**: Debug port exposes browser to any local application. Don't browse sensitive sites.

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

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────┐
│              CHROME DEVTOOLS MCP CHEAT SHEET                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PERFORMANCE            NETWORK               DEBUGGING          │
│  ───────────            ───────               ─────────          │
│  performance_start_     list_network_         list_console_      │
│    trace                  requests              messages         │
│  performance_stop_      get_network_          evaluate_script    │
│    trace                  request             take_screenshot    │
│  performance_analyze_                         take_snapshot      │
│    insight                                                       │
│                                                                  │
│  AUTOMATION             NAVIGATION            EMULATION          │
│  ──────────             ──────────            ─────────          │
│  click, fill            navigate_page         emulate            │
│  fill_form, hover       new_page, close_page  resize_page        │
│  press_key, drag        list_pages, select_                      │
│  upload_file              page, wait_for                         │
│  handle_dialog                                                   │
│                                                                  │
│  QUICK PROMPTS                                                   │
│  ─────────────                                                   │
│  "Check performance of [url]"                                    │
│  "Show console errors on [url]"                                  │
│  "Take screenshot at mobile viewport"                            │
│  "Fill form and submit"                                          │
│  "Debug CORS issues on [url]"                                    │
│                                                                  │
│  INSTALLATION                                                    │
│  ────────────                                                    │
│  claude mcp add --scope user chrome-devtools \                   │
│    npx chrome-devtools-mcp@latest                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Resources

- [Official Repository](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [npm Package](https://npmjs.org/package/chrome-devtools-mcp)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
