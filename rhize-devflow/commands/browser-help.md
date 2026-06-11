# /rhize-devflow:browser-help

Quick reference for Chrome DevTools MCP skill.

## Aliases
- `@browser-help`
- `/rhize-devflow:browser-help`

## Available Commands

| Command | Purpose |
|---------|---------|
| `/rhize-devflow:browser-perf [url]` | Performance analysis (Core Web Vitals) |
| `/rhize-devflow:browser-debug [url]` | Network & console debugging |
| `/rhize-devflow:browser-test [url]` | Visual & form testing |
| `/rhize-devflow:browser-help` | This help reference |

## Quick Prompts

### Performance
```
Check the performance of http://localhost:3000
Check performance with mobile emulation
Analyze LCP for the dashboard page
```

### Network/Debugging
```
Show me all network requests on http://localhost:3000/api
Debug CORS issues on the checkout page
Show console errors for http://localhost:3000
```

### Visual Testing
```
Take a screenshot of http://localhost:3000/pricing
Test responsive layouts at mobile, tablet, desktop
Take screenshots of the homepage at all breakpoints
```

### Form Automation
```
Fill the login form and submit
Test the signup flow with test data
Fill the contact form: name=Test, email=test@test.com
```

### Multi-Page
```
Open http://localhost:3000 and http://localhost:3000/about in tabs
Navigate through the checkout flow
Test navigation between dashboard pages
```

## MCP Tools Reference

### Input Automation
- `click` - Click element
- `fill` - Fill input field
- `fill_form` - Fill multiple fields
- `hover` - Hover over element
- `press_key` - Send keyboard event
- `drag` - Drag between elements
- `upload_file` - Upload to file input
- `handle_dialog` - Handle JS dialogs

### Navigation
- `navigate_page` - Go to URL
- `new_page` - Open new tab
- `close_page` - Close tab
- `list_pages` - List open tabs
- `select_page` - Switch tab
- `wait_for` - Wait for condition

### Performance
- `performance_start_trace` - Begin recording
- `performance_stop_trace` - Stop and get data
- `performance_analyze_insight` - Analyze insight

### Network
- `list_network_requests` - Get all requests
- `get_network_request` - Get request details

### Debugging
- `list_console_messages` - Get console output
- `get_console_message` - Get message details
- `evaluate_script` - Run JS in page
- `take_screenshot` - Capture image
- `take_snapshot` - Accessibility tree

### Emulation
- `emulate` - Emulate device
- `resize_page` - Change viewport

## Installation

```bash
# Claude Code (user scope)
claude mcp add --scope user chrome-devtools npx chrome-devtools-mcp@latest

# Verify
curl http://127.0.0.1:9222/json/version
```

## Configuration

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

### Common Options
- `--headless=true` - Run without visible browser
- `--isolated=true` - Use temporary profile
- `--viewport=1440x900` - Set initial viewport
- `--browser-url=http://127.0.0.1:9222` - Connect to running Chrome

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Browser won't launch | Check Node.js v20.19+, try `--browser-url` |
| Connection refused | Kill existing Chrome, check port 9222 |
| Screenshots blank | Add `--disable-gpu` Chrome arg |
| Element not found | Add `wait_for` before interaction |

## Resources

- [Skill Documentation](../SKILL.md)
- [Examples](../references/EXAMPLES.md)
- [Troubleshooting](../references/TROUBLESHOOTING.md)
- [Official Repo](https://github.com/ChromeDevTools/chrome-devtools-mcp)
