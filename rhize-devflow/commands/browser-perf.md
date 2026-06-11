# /rhize-devflow:browser-perf

Run performance analysis on a URL using Chrome DevTools MCP.

## Aliases
- `@browser-perf`
- `/rhize-devflow:browser-perf`

## Usage
```
/rhize-devflow:browser-perf [url]
/rhize-devflow:browser-perf http://localhost:3000/dashboard
/rhize-devflow:browser-perf --mobile http://localhost:3000
```

## What This Command Does

1. **Setup Phase**
   - Verify Chrome DevTools MCP server is available
   - Configure viewport (desktop default, mobile if --mobile)
   - Navigate to target URL

2. **Recording Phase**
   - Start performance trace
   - Wait for page load (networkidle2)
   - Optionally scroll page to trigger lazy content
   - Stop trace

3. **Analysis Phase**
   - Analyze performance insights
   - Extract Core Web Vitals (LCP, FID/INP, CLS)
   - Identify render-blocking resources
   - Check for layout shifts

4. **Output**
   - Return summary to chat
   - Provide actionable recommendations
   - List specific problematic resources

## MCP Tools Used

- `navigate_page` - Load target URL
- `emulate` - Set device (if --mobile)
- `performance_start_trace` - Begin recording
- `performance_stop_trace` - End recording
- `performance_analyze_insight` - Get recommendations

## Expected Output

```
## Performance Analysis: http://localhost:3000/dashboard

**Core Web Vitals:**
- LCP: 2.1s ⚠️ (target: < 2.5s)
- FID: 45ms ✅ (target: < 100ms)
- CLS: 0.08 ✅ (target: < 0.1)

**Issues Found:**
1. 🔴 Render-blocking CSS: /styles/main.css (1.2s)
2. 🟡 Large image not lazy-loaded: hero-banner.jpg (450KB)
3. 🟡 Unused JavaScript: 35% of bundle unused

**Recommendations:**
- Inline critical CSS, defer non-critical
- Add loading="lazy" to below-fold images
- Enable code splitting for route-based chunks
```

## Follow-up Actions

After analysis:
- `@browser-debug [url]` - Check network/console for more details
- `@browser-test [url]` - Visual regression testing
- Run again with `--mobile` for mobile performance

## Notes

- First run may be slower (Chrome launch)
- Use `--isolated` in MCP config for consistent results
- Performance varies; run multiple times for baseline
