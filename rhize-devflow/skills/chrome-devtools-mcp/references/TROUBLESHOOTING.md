# Chrome DevTools MCP - Troubleshooting Guide

> Common issues and solutions for Chrome DevTools MCP Server

---

## Installation Issues

### MCP Server Not Starting

**Symptoms:**
- "Failed to connect to MCP server"
- "Command not found: npx"
- Timeout on startup

**Solutions:**

1. **Verify Node.js version:**
   ```bash
   node --version  # Must be v20.19 or higher
   ```

2. **Clear npm cache:**
   ```bash
   npm cache clean --force
   ```

3. **Install explicitly:**
   ```bash
   npm install -g chrome-devtools-mcp@latest
   ```

### Browser Doesn't Launch

**Symptoms:**
- "No browser instance found"
- "Failed to launch Chrome"

**Solutions:**

1. **macOS sandbox issues:**
   - Grant Terminal/IDE full disk access in System Preferences
   - Try `--browser-url` to connect to manually started Chrome

2. **Specify Chrome path explicitly:**
   ```json
   {
     "args": ["-y", "chrome-devtools-mcp@latest",
       "--executablePath=/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
   }
   ```

---

## Connection Issues

### Port Already in Use

**Symptoms:**
- "Address already in use: 9222"

**Solutions:**

1. **Find and kill existing Chrome debug process:**
   ```bash
   # macOS/Linux
   lsof -i :9222
   kill -9 <PID>
   ```

2. **Use a different port:**
   ```bash
   chrome --remote-debugging-port=9223 --user-data-dir=/tmp/chrome-9223
   ```

### Cannot Connect to Running Chrome

**Symptoms:**
- "Connection refused"

**Solutions:**

1. **Verify Chrome is running with debug port:**
   ```bash
   curl http://127.0.0.1:9222/json/version
   # Should return JSON with Chrome version
   ```

2. **Check Chrome was started correctly:**
   ```bash
   # Must include BOTH flags
   chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug
   ```

---

## Runtime Issues

### Tools Timing Out

**Solutions:**

1. **Use appropriate wait conditions:**
   ```markdown
   Bad:  "Navigate to http://slow-site.com"
   Good: "Navigate to http://slow-site.com with waitUntil: networkidle2"
   ```

2. **Add explicit waits:**
   ```markdown
   "Navigate to http://localhost:3000, wait for selector '.content' 
   to be visible, then take a screenshot"
   ```

### Screenshots Are Blank/Black

**Solutions:**

1. **Headless mode GPU issues:**
   ```json
   {
     "args": ["-y", "chrome-devtools-mcp@latest",
       "--headless=true", "--chromeArg=--disable-gpu"]
   }
   ```

2. **Wait for content:**
   ```markdown
   "Navigate to http://localhost:3000, wait 2 seconds, then take screenshot"
   ```

### Element Not Found

**Solutions:**

1. **Wait for element:**
   ```markdown
   "Navigate to http://localhost:3000/dynamic, wait for selector 
   '.dynamic-element' to be visible, then click it"
   ```

2. **Check selector validity:**
   ```markdown
   "Navigate to http://localhost:3000, evaluate: 
   document.querySelectorAll('.my-selector').length"
   ```

---

## Platform-Specific Issues

### macOS

**Gatekeeper blocking Chrome:**
```bash
xattr -d com.apple.quarantine /Applications/Google\ Chrome.app
```

**Terminal needs permissions:**
- System Preferences > Security & Privacy > Privacy
- Add Terminal to Full Disk Access

### Windows

**Long path issues:**
```json
{
  "args": ["-y", "chrome-devtools-mcp@latest",
    "--user-data-dir=C:\\temp\\cdp"]
}
```

### Linux

**No sandbox mode (if required):**
```json
{
  "args": ["-y", "chrome-devtools-mcp@latest",
    "--chromeArg=--no-sandbox", "--chromeArg=--disable-setuid-sandbox"]
}
```

**Display issues (headless server):**
```bash
sudo apt-get install xvfb
xvfb-run npx chrome-devtools-mcp@latest
```

---

## Debug Logging

### Enable Verbose Logs

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest",
        "--logFile=/tmp/chrome-devtools-mcp.log"],
      "env": { "DEBUG": "*" }
    }
  }
}
```

### Report Issues

When reporting issues, include:
1. Debug log file
2. Chrome version (`chrome://version`)
3. Node.js version (`node --version`)
4. OS and version
5. MCP client being used

Submit: https://github.com/ChromeDevTools/chrome-devtools-mcp/issues

---

## Quick Diagnostic Commands

```bash
# Check Node version
node --version

# Test Chrome debug port
curl http://127.0.0.1:9222/json/version

# List Chrome processes
ps aux | grep -i chrome

# Check port usage
lsof -i :9222  # macOS/Linux

# Test package
npx chrome-devtools-mcp@latest --help
```
