# Chrome DevTools MCP Skill

A skill for integrating Google's official Chrome DevTools MCP server into your development workflow.

## Skill Structure

```
chrome-devtools-mcp/
├── SKILL.md                    # Main skill document
├── README.md                   # This file
└── references/
    ├── EXAMPLES.md             # Detailed prompts and examples
    └── TROUBLESHOOTING.md      # Common issues and solutions
```

## Quick Start

### 1. Install MCP Server

```bash
# Claude Code (user scope - recommended)
claude mcp add --scope user chrome-devtools npx chrome-devtools-mcp@latest
```

### 2. Verify Installation

```
Check the performance of https://example.com
```

### 3. Read the Skill

See `SKILL.md` for full tool reference, configuration, and workflows.

## Use Cases

| Scenario | Primary Tools |
|----------|---------------|
| Performance testing | `performance_start_trace`, `performance_analyze_insight` |
| Form automation | `fill`, `fill_form`, `click`, `handle_dialog` |
| Network debugging | `list_network_requests`, `get_network_request` |
| Visual testing | `take_screenshot`, `emulate` |
| Error investigation | `list_console_messages`, `evaluate_script` |

## Requirements

- Node.js v20.19+
- Chrome (stable or newer)
- npm

## Resources

- [Official Repository](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [npm Package](https://npmjs.org/package/chrome-devtools-mcp)

## Version

- Skill Version: 1.0.0
- MCP Server: v0.11.0+ (@latest)
- Last Updated: December 2025
