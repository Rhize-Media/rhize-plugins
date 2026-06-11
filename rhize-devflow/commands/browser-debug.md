# /rhize-devflow:browser-debug

Debug network requests and console errors using Chrome DevTools MCP.

## Aliases
- `@browser-debug`
- `/rhize-devflow:browser-debug`

## Usage
```
/rhize-devflow:browser-debug [url]
/rhize-devflow:browser-debug http://localhost:3000/api-page
/rhize-devflow:browser-debug --action "click submit" http://localhost:3000/form
```

## What This Command Does

1. **Navigation Phase**
   - Navigate to target URL
   - Wait for page load

2. **Action Phase** (if --action specified)
   - Perform user action (click, submit, etc.)
   - Wait for network activity to settle

3. **Analysis Phase**
   - List all network requests
   - Identify failed requests (4xx, 5xx)
   - Get console messages (errors, warnings)
   - Check for CORS issues

4. **Deep Dive**
   - Get full details for failed requests
   - Extract request/response headers
   - Show error stack traces

## MCP Tools Used

- `navigate_page` - Load target URL
- `click`, `fill` - Perform actions
- `list_network_requests` - Get all requests
- `get_network_request` - Get request details
- `list_console_messages` - Get console output

## Expected Output

```
## Debug Report: http://localhost:3000/checkout

**Network Requests:** 23 total, 2 failed

**Failed Requests:**
1. 🔴 POST /api/payment → 403 Forbidden
   - Missing: Authorization header
   - Response: {"error": "Token expired"}

2. 🔴 GET /api/user/profile → 500 Internal Server Error
   - Response: {"error": "Database connection failed"}

**Console Errors:**
1. TypeError: Cannot read property 'map' of undefined
   at ProductList.tsx:45
   
2. CORS: Access-Control-Allow-Origin missing
   for https://api.external.com/data

**CORS Issues Detected:**
- https://api.external.com blocked (no CORS headers)

**Recommendations:**
- Check auth token refresh logic
- Add CORS proxy or configure allowed origins
- Handle null/undefined in ProductList component
```

## Follow-up Actions

After debugging:
- Fix identified issues in code
- `@browser-debug` again to verify fixes
- `@browser-test` to ensure visual correctness

## Common Debug Scenarios

| Issue | What to Look For |
|-------|------------------|
| CORS | `Access-Control-*` headers in response |
| Auth | 401/403 status, token in request headers |
| API Errors | 5xx status, response body for error message |
| Client Errors | Console errors with stack traces |
